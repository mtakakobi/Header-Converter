import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Inches
import io
import zipfile
import os

st.set_page_config(page_title="Batch Header Replacer", layout="centered")
st.title("Batch Document Header Replacer")
st.caption("Upload .docx or .pdf files. Pages without headers are skipped automatically.")

DEFAULT_HEADER_PATH = "header_banner.png"

# Load default header from repository
default_header_bytes = None
if os.path.exists(DEFAULT_HEADER_PATH):
    with open(DEFAULT_HEADER_PATH, "rb") as f:
        default_header_bytes = f.read()

# Optional header uploader (defaults to the repository image if left empty)
custom_banner_file = st.file_uploader(
    "Custom Header Banner (Optional — defaults to standard company banner)", 
    type=["png", "jpg", "jpeg"]
)

# Determine active header banner
if custom_banner_file:
    active_header_bytes = custom_banner_file.read()
    st.info("Using custom uploaded header banner.")
elif default_header_bytes:
    active_header_bytes = default_header_bytes
    st.image(active_header_bytes, caption="Active Default Header Banner", use_container_width=True)
else:
    active_header_bytes = None
    st.warning("⚠️ No default 'header_banner.png' found in the project root. Please upload a banner to continue.")

uploaded_files = st.file_uploader(
    "Drop daily reports here (.docx, .pdf)", 
    accept_multiple_files=True, 
    type=["docx", "pdf"]
)

def process_pdf(file_bytes, banner_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    for page in doc:
        header_rect = fitz.Rect(0, 0, page.rect.width, 85)
        
        # Detect text, vector graphics, or images in header zone
        text_in_header = page.get_text("text", clip=header_rect).strip()
        drawings_in_header = [d for d in page.get_drawings() if header_rect.intersects(d["rect"])]
        images_in_header = []
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            for img_rect in page.get_image_rects(xref):
                if header_rect.intersects(img_rect):
                    images_in_header.append(img_rect)
        
        # SKIP if no header elements exist on this page
        if not (text_in_header or drawings_in_header or images_in_header):
            continue
            
        # Overwrite header
        page.draw_rect(header_rect, color=None, fill=(1, 1, 1), overlay=True)
        banner_rect = fitz.Rect(36, 12, page.rect.width - 36, 75)
        page.insert_image(banner_rect, stream=banner_bytes, keep_proportion=True)
        
    out_pdf = io.BytesIO()
    doc.save(out_pdf)
    return out_pdf.getvalue()

def process_docx(file_bytes, banner_bytes):
    doc = Document(io.BytesIO(file_bytes))
    for section in doc.sections:
        has_text = any(p.text.strip() for p in section.header.paragraphs)
        has_tables = len(section.header.tables) > 0
        has_images = bool(section.header._element.xpath('.//a:blip') or section.header._element.xpath('.//w:drawing'))
        
        # SKIP if no header elements exist in this section
        if not (has_text or has_tables or has_images):
            continue
            
        for p in section.header.paragraphs:
            p.text = ""
        for t in section.header.tables:
            t._element.getparent().remove(t._element)
            
        header_p = section.header.paragraphs[0]
        header_p.alignment = 1
        run = header_p.add_run()
        run.add_picture(io.BytesIO(banner_bytes), width=Inches(6.5))

    out_docx = io.BytesIO()
    doc.save(out_docx)
    return out_docx.getvalue()

# Processing button
if uploaded_files and active_header_bytes and st.button("Process & Download All", type="primary"):
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file in uploaded_files:
            file_bytes = file.read()
            if file.name.endswith(".pdf"):
                processed = process_pdf(file_bytes, active_header_bytes)
            elif file.name.endswith(".docx"):
                processed = process_docx(file_bytes, active_header_bytes)
            else:
                continue
            zip_file.writestr(f"client_{file.name}", processed)
            
    st.success(f"Processed {len(uploaded_files)} file(s) successfully!")
    st.download_button(
        label="📥 Download Ready Files (ZIP)",
        data=zip_buffer.getvalue(),
        file_name="client_ready_reports.zip",
        mime="application/zip"
    )