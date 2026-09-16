import streamlit as st
import fitz  # PyMuPDF
from PIL import Image, ImageDraw
import io
import os
from streamlit_drawable_canvas import st_canvas

st.set_page_config(page_title="ABAS Dossier Compiler & Editor", layout="wide")
st.title("Bulk Loading Dossier Compiler & Visual Editor")

DEFAULT_HEADER_PATH = "header_banner.png"

# Load default banner
default_header_bytes = None
if os.path.exists(DEFAULT_HEADER_PATH):
    with open(DEFAULT_HEADER_PATH, "rb") as f:
        default_header_bytes = f.read()

# Initialize Session State
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = None
if "current_page" not in st.session_state:
    st.session_state.current_page = 0

def stamp_header_banner(page, banner_bytes, custom_rect=None):
    """Masks header area and stamps ABAS banner using auto or custom coordinates."""
    p_w = page.rect.width
    p_h = page.rect.height
    is_landscape = p_w > p_h
    
    if custom_rect:
        header_rect = custom_rect
        banner_box = custom_rect
    else:
        header_height = p_h * 0.12 if is_landscape else p_h * 0.095
        header_rect = fitz.Rect(0, 0, p_w, header_height)
        margin_x = 40 if not is_landscape else 50
        banner_box = fitz.Rect(margin_x, 12, p_w - margin_x, header_height - 6)
    
    page.draw_rect(header_rect, color=None, fill=(1, 1, 1), overlay=True)
    page.insert_image(banner_box, stream=banner_bytes, keep_proportion=True)

def process_master_doc(file_bytes):
    src = fitz.open(stream=file_bytes, filetype="pdf")
    reordered_doc = fitz.open()
    
    survey_pages = []
    sof_pages = []
    manifest_pages = []
    stowage_pages = []
    other_pages = []
    
    for i in range(len(src)):
        page = src[i]
        txt = page.get_text("text").upper()
        if "DRAUGHT SURVEY" in txt or "DRAFT STATEMENT" in txt:
            survey_pages.append(i)
        elif "STATEMENT OF FACT" in txt or "TIME SHEET" in txt:
            sof_pages.append(i)
        elif "CARGO MANIFEST" in txt:
            manifest_pages.append(i)
        elif "STOWAGE PLAN" in txt:
            stowage_pages.append(i)
        else:
            other_pages.append(i)
            
    target_indices = survey_pages + sof_pages + manifest_pages + stowage_pages + other_pages
    if len(target_indices) != len(src):
        target_indices = list(range(len(src)))
        
    for idx in target_indices:
        reordered_doc.insert_pdf(src, from_page=idx, to_page=idx)
    return reordered_doc

def process_fc_package(file_bytes, banner_bytes):
    src = fitz.open(stream=file_bytes, filetype="pdf")
    processed_doc = fitz.open()
    
    summary_page_idx = None
    log_page_indices = []
    
    for i in range(len(src)):
        page = src[i]
        txt = page.get_text("text").upper()
        is_summary = any(k in txt for k in ["STATEMENT CARGO LOADING", "STATEMENT OF FACT TRANSHIPMENT", "TOTAL CARGO TRANSHIPMENT"])
        is_internal_ba = "BERITA ACARA" in txt and not is_summary
        
        if is_summary and summary_page_idx is None:
            summary_page_idx = i
        elif not is_internal_ba:
            log_page_indices.append(i)
            
    if summary_page_idx is not None:
        processed_doc.insert_pdf(src, from_page=summary_page_idx, to_page=summary_page_idx)
        stamp_header_banner(processed_doc[0], banner_bytes)
        
    for l_idx in log_page_indices:
        if l_idx != summary_page_idx:
            processed_doc.insert_pdf(src, from_page=l_idx, to_page=l_idx)
            
    return processed_doc

# ----------------- SIDEBAR: COMPILATION & FILE CONTROL -----------------
with st.sidebar:
    st.header("1. Upload & Compile")
    master_file = st.file_uploader("Master Vessel Doc", type=["pdf"])
    fc_files = st.file_uploader("Floating Crane Packages", type=["pdf"], accept_multiple_files=True)
    vessel_name = st.text_input("Vessel Name", value="MV DONG FANG FU TAI")
    
    if master_file and fc_files and default_header_bytes:
        if st.button("🚀 Compile Initial Dossier", type="primary", use_container_width=True):
            final_dossier = fitz.open()
            
            # Master
            m_doc = process_master_doc(master_file.read())
            final_dossier.insert_pdf(m_doc)
            
            # Cranes
            for fc in fc_files:
                c_doc = process_fc_package(fc.read(), default_header_bytes)
                final_dossier.insert_pdf(c_doc)
                
            out_buf = io.BytesIO()
            final_dossier.save(out_buf)
            st.session_state.pdf_bytes = out_buf.getvalue()
            st.session_state.current_page = 0
            st.rerun()

    if st.session_state.pdf_bytes:
        st.divider()
        clean_name = f"LOADING DOC {vessel_name.strip().upper()}.pdf"
        st.download_button(
            label=f"📥 Download Finished PDF",
            data=st.session_state.pdf_bytes,
            file_name=clean_name,
            mime="application/pdf",
            use_container_width=True
        )

# ----------------- MAIN PANEL: VIEWER & EDITING SUITE -----------------
if st.session_state.pdf_bytes:
    doc = fitz.open(stream=st.session_state.pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    
    # Page Navigation Bar
    col_nav1, col_nav2, col_nav3 = st.columns([1, 3, 1])
    with col_nav1:
        if st.button("◀ Previous Page") and st.session_state.current_page > 0:
            st.session_state.current_page -= 1
            st.rerun()
    with col_nav2:
        selected_p = st.selectbox(
            "Go to Page", 
            options=range(1, total_pages + 1), 
            index=st.session_state.current_page
        )
        if selected_p - 1 != st.session_state.current_page:
            st.session_state.current_page = selected_p - 1
            st.rerun()
    with col_nav3:
        if st.button("Next Page ▶") and st.session_state.current_page < total_pages - 1:
            st.session_state.current_page += 1
            st.rerun()

    current_idx = st.session_state.current_page
    page = doc[current_idx]
    p_w = int(page.rect.width)
    p_h = int(page.rect.height)
    is_landscape = p_w > p_h
    
    st.subheader(f"Page {current_idx + 1} of {total_pages} ({'Landscape' if is_landscape else 'Portrait'} — {p_w}x{p_h} pt)")
    
    # ----------------- HEADER POSITION & SIZE CONTROLS -----------------
    with st.expander("📐 Header Position & Resize Controls", expanded=True):
        st.caption("Adjust the sliders below to move and scale the header placement box.")
        c1, c2, c3, c4 = st.columns(4)
        
        default_x = 40 if not is_landscape else 50
        default_y = 10
        default_w = p_w - (default_x * 2)
        default_h = int(p_h * 0.08)
        
        with c1:
            hdr_x = st.slider("X Position (Left Offset)", 0, p_w - 50, default_x, step=5)
        with c2:
            hdr_y = st.slider("Y Position (Top Offset)", 0, p_h - 30, default_y, step=5)
        with c3:
            hdr_w = st.slider("Width", 50, p_w - hdr_x, min(default_w, p_w - hdr_x), step=5)
        with c4:
            hdr_h = st.slider("Height", 15, int(p_h * 0.35), default_h, step=2)

        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1.5, 2, 2.5])
        with ctrl_col1:
            show_guide = st.checkbox("Show Placement Box", value=True)
        with ctrl_col2:
            if st.button("⚡ Apply Custom Placed Header", type="primary"):
                custom_box = fitz.Rect(hdr_x, hdr_y, hdr_x + hdr_w, hdr_y + hdr_h)
                stamp_header_banner(page, default_header_bytes, custom_rect=custom_box)
                out_buf = io.BytesIO()
                doc.save(out_buf)
                st.session_state.pdf_bytes = out_buf.getvalue()
                st.success("Custom header applied!")
                st.rerun()
        with ctrl_col3:
            if st.button("🔄 Auto-Fit Default Header"):
                stamp_header_banner(page, default_header_bytes)
                out_buf = io.BytesIO()
                doc.save(out_buf)
                st.session_state.pdf_bytes = out_buf.getvalue()
                st.success("Default auto header applied!")
                st.rerun()

    # Render PDF page to PIL Image
    pix = page.get_pixmap(dpi=150)
    page_image = Image.open(io.BytesIO(pix.tobytes("png")))
    
    # Draw interactive staging rectangle preview if enabled
    preview_image = page_image.copy()
    if show_guide:
        draw = ImageDraw.Draw(preview_image)
        scale_x = preview_image.width / p_w
        scale_y = preview_image.height / p_h
        
        box_coords = [
            hdr_x * scale_x,
            hdr_y * scale_y,
            (hdr_x + hdr_w) * scale_x,
            (hdr_y + hdr_h) * scale_y
        ]
        # Red bounding guide with translucent indicator
        draw.rectangle(box_coords, outline="red", width=3)
        draw.text((box_coords[0] + 8, box_coords[1] + 8), "HEADER POSITION PREVIEW", fill="red")

    # ----------------- WHITEOUT & DRAWING TOOLBAR -----------------
    st.divider()
    tb_col1, tb_col2 = st.columns([2, 1])
    with tb_col1:
        stroke_width = st.slider("Eraser / Whiteout Brush Size", 5, 50, 15)
    with tb_col2:
        apply_erasure = st.button("💾 Save Whiteout / Drawings", type="secondary")

    st.caption("Paint directly over scanner artifacts or unwanted text to white them out.")
    
    canvas_w = 750
    canvas_h = int(preview_image.height * (canvas_w / preview_image.width))
    
    canvas_result = st_canvas(
        fill_color="rgba(255, 255, 255, 1.0)",
        stroke_width=stroke_width,
        stroke_color="#FFFFFF",
        background_image=preview_image,
        update_streamlit=True,
        height=canvas_h,
        width=canvas_w,
        drawing_mode="freedraw",
        key=f"canvas_{current_idx}_{hdr_x}_{hdr_y}_{hdr_w}_{hdr_h}_{show_guide}"
    )

    # Save brush strokes directly back into the PDF page
    if apply_erasure and canvas_result.image_data is not None:
        mask = Image.fromarray(canvas_result.image_data.astype("uint8"), "RGBA")
        if mask.getbbox():
            base_rgb = page_image.resize((canvas_w, canvas_h))
            base_rgb.paste(mask, (0, 0), mask)
            
            img_byte_arr = io.BytesIO()
            base_rgb.save(img_byte_arr, format="PNG")
            
            page.clean_contents()
            page.draw_rect(page.rect, color=None, fill=(1, 1, 1), overlay=True)
            page.insert_image(page.rect, stream=img_byte_arr.getvalue())
            
            out_buf = io.BytesIO()
            doc.save(out_buf)
            st.session_state.pdf_bytes = out_buf.getvalue()
            st.success("Edits saved!")
            st.rerun()

else:
    st.info("👈 Upload your Master Vessel document and Floating Crane packages in the sidebar to begin.")