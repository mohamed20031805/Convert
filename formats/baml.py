python -c "
import pdfplumber
p = r'T:\Dallas\CSS-BOC\CTL\REC\Réconciliation dérivés listés\FUND CHANNEL\2026\BAML\MSIM_SG_EOD Daily Statement.pdf'
with pdfplumber.open(p) as pdf:
    for i, page in enumerate(pdf.pages[1:4]):  # pages 2,3,4
        texte = page.extract_text() or ''
        print(f'--- PAGE {i+2} ---')
        for j, ligne in enumerate(texte.split('\n')):
            print(f'[{j}] {ligne}')
        print()
"
