import streamlit as st
import fitz  # PyMuPDF
import io
import os

st.set_page_config(page_title="ABAS Loading Doc Compiler", layout="centered")
st.title("Bulk Loading Dossier Compiler")
st.caption("Upload the 3 source files to automatically reorder, white-label subcon summaries, and compile the final Loading Doc.")

DEFAULT_HEADER_PATH = "header_banner.png"

# Load default banner
default_header_bytes = None
if os.path.exists(DEFAULT_HEADER_PATH):
    with open(DEFAULT_HEADER_PATH, "rb") as f:
        default_header_bytes = f.read()

# Header status
if default_header_bytes:
    st.image(default_header_bytes, caption="Active ABAS Header Banner", use_container_width=True)
else:
    st.warning("⚠️ 'header_banner.png' not found in project root. Please ensure it is placed next to app.py.")

# Three specific file inputs
st.subheader("1. Source Documents")
master_file = st.file_uploader("1. Master Vessel Doc (Survey, SOF, Manifest, Stowage)", type=["pdf"])
fc1_file = st.file_uploader("2. Floating Crane 1 (e.g., FC GUANG TAI 03)", type=["pdf"])
fc2_file = st.file_uploader("3. Floating Crane 2 (Optional - e.g., FC MSN 7)", type=["pdf"])

vessel_name = st.text_input("Vessel Name for Output File", value="MV DONG FANG FU TAI")

def stamp_header_banner(page, banner_bytes):
    """Masks top subcontractor header area and stamps the clean ABAS banner."""
    p_w = page.rect.width
    p_h = page.rect.height
    is_landscape = p_w > p_h
    
    # Target top 12% for landscape, 9.5% for portrait
    header_height = p_h * 0.12 if is_landscape else p_h * 0.095
    header_rect = fitz.Rect(0, 0, p_w, header_height)
    
    # Whiteout subcontractor letterhead
    page.draw_rect(header_rect, color=None, fill=(1, 1, 1), overlay=True)
    
    # Stamp ABAS banner
    margin_x = 40 if not is_landscape else 50
    banner_box = fitz.Rect(margin_x, 12, p_w - margin_x, header_height - 6)
    page.insert_image(banner_box, stream=banner_bytes, keep_proportion=True)

def process_master_doc(file_bytes):
    """
    Reorders master doc to standard sequence:
    1. Draught Survey (Anindya)
    2. Statement of Fact & Time Sheets (ABT)
    3. Cargo Manifest (IDT)
    4. Stowage Plan (IDT)
    """
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
            
    # Assembly order
    target_indices = survey_pages + sof_pages + manifest_pages + stowage_pages + other_pages
    
    # Fallback to original order if OCR/text search didn't match
    if len(target_indices) != len(src):
        target_indices = list(range(len(src)))
        
    for idx in target_indices:
        reordered_doc.insert_pdf(src, from_page=idx, to_page=idx)
        
    return reordered_doc

def process_fc_package(file_bytes, banner_bytes):
    """
    Extracts the summary sheet (white-labels it) and the hourly logs.
    Discards redundant internal subcon 'Berita Acara' sheets.
    """
    src = fitz.open(stream=file_bytes, filetype="pdf")
    processed_doc = fitz.open()
    
    summary_page_idx = None
    log_page_indices = []
    
    for i in range(len(src)):
        page = src[i]
        txt = page.get_text("text").upper()
        
        # Identify the main summary sheet
        is_summary = any(k in txt for k in ["STATEMENT CARGO LOADING", "STATEMENT OF FACT TRANSHIPMENT", "TOTAL CARGO TRANSHIPMENT"])
        # Check if page is an auxiliary subcon Berita Acara (e.g. Sisa RC Barge / Internal BA)
        is_internal_ba = "BERITA ACARA" in txt and not is_summary
        
        if is_summary and summary_page_idx is None:
            # Check if this is the clean or subcon version; prefer whichever contains the summary table
            summary_page_idx = i
        elif not is_internal_ba:
            # Operational logs (Transshipment Statement of Facts)
            log_page_indices.append(i)
            
    # 1. Insert Summary Sheet (White-labeled)
    if summary_page_idx is not None:
        processed_doc.insert_pdf(src, from_page=summary_page_idx, to_page=summary_page_idx)
        stamp_header_banner(processed_doc[0], banner_bytes)
        
    # 2. Append Hourly Logs (Untouched)
    for l_idx in log_page_indices:
        if l_idx != summary_page_idx:
            processed_doc.insert_pdf(src, from_page=l_idx, to_page=l_idx)
            
    return processed_doc

if master_file and fc1_file and default_header_bytes:
    if st.button("🚀 Compile Loading Document", type="primary"):
        with st.spinner("Compiling dossier..."):
            final_dossier = fitz.open()
            
            # Step 1: Process and insert Master Vessel Doc
            master_doc = process_master_doc(master_file.read())
            final_dossier.insert_pdf(master_doc)
            
            # Step 2: Process and insert FC 1
            fc1_doc = process_fc_package(fc1_file.read(), default_header_bytes)
            final_dossier.insert_pdf(fc1_doc)
            
            # Step 3: Process and insert FC 2 (if uploaded)
            if fc2_file:
                fc2_doc = process_fc_package(fc2_file.read(), default_header_bytes)
                final_dossier.insert_pdf(fc2_doc)
                
            out_pdf = io.BytesIO()
            final_dossier.save(out_pdf)
            out_bytes = out_pdf.getvalue()
            
            clean_name = f"LOADING DOC {vessel_name.strip().upper()}.pdf"
            
            st.success(f"Dossier created successfully! Total: {len(final_dossier)} pages.")
            st.download_button(
                label=f"📥 Download {clean_name}",
                data=out_bytes,
                file_name=clean_name,
                mime="application/pdf"
            )