import re

def detecter(texte_page1):
    """Retourne True si c'est un PDF Triton"""
    return "OPEN POSITIONS STATEMENT" in texte_page1

def extraire_entete(chemin_pdf, template_json=None):
    import pdfplumber, json, os
    with pdfplumber.open(chemin_pdf) as pdf:
        lignes = pdf.pages[0].extract_text().split("\n")

    infos = {"Broker": "", "Client": "", "Close of Business": "", "Account": ""}

    if template_json and os.path.exists(template_json):
        with open(template_json) as f:
            infos.update(json.load(f))

    for ligne in lignes:
        ligne = ligne.strip()
        m = re.search(r'ACCOUNT\s*:\s*(\S+)', ligne)
        if m and not infos["Account"]:
            infos["Account"] = m.group(1).strip()
        m = re.search(r'ATHENS\s*,\s*(\d{2}/\d{2}/\d{2})', ligne)
        if m and not infos["Close of Business"]:
            infos["Close of Business"] = m.group(1).strip()
        if "Derivatives" in ligne and not infos["Broker"]:
            infos["Broker"] = ligne.strip()
        if not infos["Client"] and re.match(r'^[A-Z]', ligne):
            if not any(x in ligne for x in ["STATEMENT","Athens","ACCOUNT","ATHENS","VALAORITOU"]):
                infos["Client"] = ligne.strip()

    print(f"\n✅ Entête Triton : {infos}")
    return infos

def extraire_positions(chemin_pdf):
    import pdfplumber
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text()
            if not texte or "OPEN POSITIONS STATEMENT" not in texte:
                continue

            tables = page.extract_tables()
            for table in tables:
                if not table or len(table[0]) < 6:
                    continue
                headers = [str(h).replace("\n", " ") if h else "" for h in table[0]]
                if "LONG" not in " ".join(headers):
                    continue

                # Passe 1 : trouver Contract et Maturity
                current_contract = ""
                current_maturity = ""
                mon = yr = ""

                for row in table[1:]:
                    if not row: continue
                    if row[0] and str(row[0]).strip() and "TOTAL" not in str(row[0]):
                        current_contract = str(row[0]).strip()
                    if row[1] and str(row[1]).strip() and "TOTAL" not in str(row[1]):
                        current_maturity = str(row[1]).strip()
                        m = re.match(r'([A-Z]+)\s+(\d{4})', current_maturity)
                        if m:
                            mon = m.group(1)
                            yr  = m.group(2)

                # Passe 2 : extraire les données
                for row in table[1:]:
                    if not row or not any(row): continue
                    if "TOTAL" in " ".join(str(c) for c in row if c): continue

                    trade_date   = str(row[3]).strip() if row[3] else ""
                    trade_number = str(row[4]).strip() if row[4] else ""
                    long_val     = str(row[5]).strip() if row[5] else ""
                    short_val    = str(row[6]).strip() if row[6] else ""

                    if not re.match(r'\d{2}/\d{2}/\d{2}', trade_date): continue
                    if not long_val and not short_val: continue

                    toutes_les_lignes.append({
                        "Trade Date":   trade_date,
                        "Trade Number": trade_number,
                        "Long":         long_val,
                        "Short":        short_val,
                    })

    print(f"\n📊 Triton - Total lignes : {len(toutes_les_lignes)}")
    return toutes_les_lignes

def formater_output(lignes):
    """Retourne un DataFrame détaillé (pas d'agrégation pour Triton)"""
    import pandas as pd
    df = pd.DataFrame(lignes)
    df["Long"]  = pd.to_numeric(df["Long"],  errors="coerce").fillna(0).astype(int)
    df["Short"] = pd.to_numeric(df["Short"], errors="coerce").fillna(0).astype(int)
    df["Long"]  = df["Long"].replace(0, "")
    df["Short"] = df["Short"].replace(0, "")
    return df[["Trade Date", "Trade Number", "Long", "Short"]]