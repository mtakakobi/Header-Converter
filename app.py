import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Inches
import io
import zipfile
import os

st.set_page_config(page_title="ABAS Header Replacer", layout="centered")
st.title("Batch Document Header Replacer")
st.caption("Upload .docx or .pdf files. Only pages containing an existing header will be replaced.")

# Check for default header file in the repo or allow user override
default_header_path = "Header Abas.png"
if os.path.exists(default_header_path):
    with open(default_header_path, "rb") as f:
        default_header_bytes = f.read()
    st.image(default_header_bytes, caption="Active Header Banner", use_container_width=True)
    header_bytes = default_header_bytes
else:
    uploaded_banner = st.file_uploader("Upload Header Banner (.png)", type=["png", "jpg", "jpeg"])
    header_bytes = uploaded_banner.read() if uploaded_banner else None

uploaded_files = st.file_uploader(
    "Drop daily reports here (.docx, .pdf)", 
    accept_multiple_files=True, 
    type=["docx", "pdf"]
)

def process_pdf(file_bytes, banner_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    for page in doc:
        # Check top 85 points of page for existing content/headers
        header_rect = fitz.Rect(0, 0, page.rect.width, 85)
        text_in_header = page.get_text("text", clip=header_rect).strip()
        drawings_in_header = [d for d in page.get_drawings() if header_rect.intersects(d["rect"])]
        
        # Only rewrite if existing header content is detected
        if text_in_header or drawings_in_header:
            # 1. Whiteout subcontractor header area
            page.draw_rect(header_rect, color=None, fill=(1, 1, 1), overlay=True)
            
            # 2. Stamp full header banner across top margin (36pt / 0.5" side margins)
            banner_rect = fitz.Rect(36, 12, page.rect.width - 36, 75)
            page.insert_image(banner_rect, stream=banner_bytes, keep_proportion=True)
            
    out_pdf = io.BytesIO()
    doc.save(out_pdf)
    return out_pdf.getvalue()

def process_pdf(file_bytes, banner_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    
    for page in doc:
        # Header scan area: top 85 points
        header_rect = fitz.Rect(0, 0, page.rect.width, 85)
        
        # 1. Check for text inside the top zone
        text_in_header = page.get_text("text", clip=header_rect).strip()
        
        # 2. Check for vector graphics or drawings
        drawings_in_header = [d for d in page.get_drawings() if header_rect.intersects(d["rect"])]
        
        # 3. Check for embedded images located in the top zone
        images_in_header = []
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            for img_rect in page.get_image_rects(xref):
                if header_rect.intersects(img_rect):
                    images_in_header.append(img_rect)
        
        # STRICT SKIP: If there is no text, drawing, or image at the top, leave page untouched
        if not (text_in_header or drawings_in_header or images_in_header):
            continue
            
        # Overwrite only when an existing header is detected
        page.draw_rect(header_rect, color=None, fill=(1, 1, 1), overlay=True)
        banner_rect = fitz.Rect(36, 12, page.rect.width - 36, 75)
        page.insert_image(banner_rect, stream=banner_bytes, keep_proportion=True)
        
    out_pdf = io.BytesIO()
    doc.save(out_pdf)
    return out_pdf.getvalue()


def process_docx(file_bytes, banner_bytes):
    doc = Document(io.BytesIO(file_bytes))
    
    for section in doc.sections:
        # Check text in header paragraphs
        has_text = any(p.text.strip() for p in section.header.paragraphs)
        # Check for tables inside the header
        has_tables = len(section.header.tables) > 0
        # Check for inline shapes/images (drawing tags in XML)
        has_images = bool(section.header._element.xpath('.//a:blip') or section.header._element.xpath('.//w:drawing'))
        
        # STRICT SKIP: If there is no text, table, or drawing, skip section
        if not (has_text or has_tables or has_images):
            continue
            
        # Clear existing header content
        for p in section.header.paragraphs:
            p.text = ""
        for t in section.header.tables:
            t._element.getparent().remove(t._element)
            
        # Insert new banner
        header_p = section.header.paragraphs[0]
        header_p.alignment = 1  # Centered
        run = header_p.add_run()
        run.add_picture(io.BytesIO(banner_bytes), width=Inches(6.5))

    out_docx = io.BytesIO()
    doc.save(out_docx)
    return out_docx.getvalue()

if uploaded_files and header_bytes and st.button("Process & Download All", type="primary"):
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file in uploaded_files:
            file_bytes = file.read()
            if file.name.endswith(".pdf"):
                processed = process_pdf(file_bytes, header_bytes)
            elif file.name.endswith(".docx"):
                processed = process_docx(file_bytes, header_bytes)
            else:
                continue
            zip_file.writestr(f"client_{file.name}", processed)
            
    st.success(f"Successfully processed {len(uploaded_files)} file(s)!")
    st.download_button(
        label="📥 Download Ready Files (ZIP)",
        data=zip_buffer.getvalue(),
        file_name="client_ready_reports.zip",
        mime="application/zip"
    )