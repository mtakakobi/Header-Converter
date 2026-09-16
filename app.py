import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Inches
import io
import zipfile

st.set_page_config(page_title="Batch Header & Logo Replacer", layout="centered")
st.title("Batch Document Header Replacer")
st.caption("Upload .docx or .pdf files. Pages without headers remain untouched.")

col1, col2 = st.columns([2, 1])
with col1:
    company_title = st.text_input("Header Title", value="Daily Activity Report")
with col2:
    logo_file = st.file_uploader("Company Logo (Optional)", type=["png", "jpg", "jpeg"])

uploaded_files = st.file_uploader("Drop daily reports here", accept_multiple_files=True, type=["docx", "pdf"])

def process_pdf(file_bytes, new_title, logo_bytes=None):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    for page in doc:
        # Check top 85 points of the page for existing header elements
        header_rect = fitz.Rect(0, 0, page.rect.width, 85)
        text_in_header = page.get_text("text", clip=header_rect).strip()
        drawings_in_header = [d for d in page.get_drawings() if header_rect.intersects(d["rect"])]
        
        # Only rewrite if existing header content is detected
        if text_in_header or drawings_in_header:
            # 1. Whiteout existing subcontractor header area
            page.draw_rect(header_rect, color=None, fill=(1, 1, 1), overlay=True)
            
            # 2. Insert logo if provided
            text_x_offset = 40
            if logo_bytes:
                logo_rect = fitz.Rect(40, 15, 110, 65)  # 70x50 box
                page.insert_image(logo_rect, stream=logo_bytes)
                text_x_offset = 125
            
            # 3. Stamp your company title
            page.insert_text((text_x_offset, 48), new_title, fontsize=13, fontname="helv", color=(0, 0, 0))
            
    out_pdf = io.BytesIO()
    doc.save(out_pdf)
    return out_pdf.getvalue()

def process_docx(file_bytes, new_title, logo_bytes=None):
    doc = Document(io.BytesIO(file_bytes))
    for section in doc.sections:
        # Check if header currently has text or embedded objects
        has_content = any(p.text.strip() for p in section.header.paragraphs) or len(section.header.tables) > 0
        
        if has_content:
            # Clear paragraphs
            for p in section.header.paragraphs:
                p.text = ""
            
            header_p = section.header.paragraphs[0]
            
            # Add logo if provided
            if logo_bytes:
                logo_stream = io.BytesIO(logo_bytes)
                run_img = header_p.add_run()
                run_img.add_picture(logo_stream, width=Inches(1.2))
                header_p.add_run("   ")  # Horizontal space
            
            # Add company title
            run_text = header_p.add_run(new_title)
            run_text.bold = True

    out_docx = io.BytesIO()
    doc.save(out_docx)
    return out_docx.getvalue()

if uploaded_files and st.button("Process & Download All", type="primary"):
    logo_data = logo_file.read() if logo_file else None
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file in uploaded_files:
            file_bytes = file.read()
            if file.name.endswith(".pdf"):
                processed = process_pdf(file_bytes, company_title, logo_data)
            elif file.name.endswith(".docx"):
                processed = process_docx(file_bytes, company_title, logo_data)
            else:
                continue
            zip_file.writestr(f"client_{file.name}", processed)
            
    st.success(f"Processed {len(uploaded_files)} files successfully!")
    st.download_button(
        label="📥 Download Ready Files (ZIP)",
        data=zip_buffer.getvalue(),
        file_name="client_ready_reports.zip",
        mime="application/zip"
    )