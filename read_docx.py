from docx import Document
import os

doc = Document(r'D:\drama\答辩PPT文案-AI漫剧智能制作平台.docx')
for i, p in enumerate(doc.paragraphs):
    if p.text.strip():
        print(f'[P{i}] {p.text}')
print('---TABLES---')
for ti, table in enumerate(doc.tables):
    print(f'Table {ti}:')
    for ri, row in enumerate(table.rows):
        cells = [c.text.strip() for c in row.cells]
        print(f'  Row {ri}: {cells}')
print('---IMAGES---')
import zipfile
z = zipfile.ZipFile(r'D:\drama\答辩PPT文案-AI漫剧智能制作平台.docx')
for name in z.namelist():
    if 'media' in name:
        print(name)
