import pdfplumber
import re
import pandas as pd

def detecter(texte):
    return "MERRILL LYNCH INTERNATIONAL" in texte

def extraire_entete(chemin_pdf, template_json=None):
    infos = {
        "Broker":            "MERRILL LYNCH INTERNATIONAL",
        "Client":            "",
        "Account":           "",
        "Close of Business": ""
    }
    with pdfplumber.open(chemin_pdf) as pdf:
        texte = pdf.pages[0].extract_text() or ""
        for ligne in texte.split('\n'):
            m = re.search(r'ACCOUNT NUMBER:\s*(\S+)', ligne)
            if m and not infos["Account"]:
                infos["Account"] = m.group(1).strip()
            m = re.search(r'STATEMENT DATE:\s*(.+)', ligne)
            if m and not infos["Close of Business"]:
                infos["Close of Business"] = m.group(1).strip()
        lignes = texte.split('\n')
        for i, ligne in enumerate(lignes):
            if "MORGAN STANLY" in ligne or "MORGAN STANLEY" in ligne:
                client_parts = []
                for j in range(i, min(i+4, len(lignes))):
                    l = lignes[j].strip()
                    if l and not any(x in l for x in ["CABOT","LONDON","UNITED","PAGE"]):
                        client_parts.append(l)
                infos["Client"] = " ".join(client_parts)
                break
    print(f"✅ Entête BAML : {infos}")
    return infos

def extraire_positions(chemin_pdf):
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            words = page.extract_words()
            if not words:
                continue

            # Regrouper par Y
            lignes_mots = {}
            for w in words:
                y = round(w['top'], 1)
                if y not in lignes_mots:
                    lignes_mots[y] = []
                lignes_mots[y].append(w)

            # Chercher entête TRADE LONG SHORT CONTRACT
            long_x = short_x = trade_x = contract_x = None
            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]
                texte_ligne = " ".join(w['text'] for w in mots)
                if "LONG" in texte_ligne and "SHORT" in texte_ligne and "TRADE" in texte_ligne and "CONTRACT" in texte_ligne:
                    for w in mots:
                        if w['text'] == "TRADE":    trade_x    = w['x0']
                        if w['text'] == "LONG":     long_x     = w['x0']
                        if w['text'] == "SHORT":    short_x    = w['x0']
                        if w['text'] == "CONTRACT": contract_x = w['x0']
                    break

            if not long_x:
                continue

            print(f"\n✅ Page {i+1} - TRADE x={trade_x}, LONG x={long_x}, SHORT x={short_x}, CONTRACT x={contract_x}")
            TOL = 20

            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]

                # Ignorer lignes totaux : contiennent "N*" ex "27*", "13*"
                texte_ligne = " ".join(w['text'] for w in mots)
                if re.search(r'\d+\*', texte_ligne):
                    continue
                if any(x in texte_ligne for x in ["AVG", "CLOSE", "TOTAL", "COMMISSION",
                    "NET PROFIT", "GROSS", "CLEARING", "BROKERAGE", "PAGE",
                    "MERRILL", "FUTURES", "KING", "LONDON", "MORGAN", "FUND",
                    "FCH", "CABOT", "UNITED", "KINGDOM", "CONFIRMATION",
                    "ACCEPTED", "PURCHASE", "SALE", "SETTL", "TRADE", "------"]):
                    continue

                # Extraire champs par position X
                trade_date   = ""
                long_val     = ""
                short_val    = ""
                contract_parts = []
                mon = yr = ccy = ""

                for w in mots:
                    x   = w['x0']
                    txt = w['text']

                    # Trade Date : x≈trade_x + format date
                    if abs(x - trade_x) < TOL and re.match(r'^\d{1,2}/\d{1,2}/\d{1,2}$', txt):
                        trade_date = txt

                    # Long : x≈long_x + petit nombre (pas date, pas prix)
                    elif abs(x - long_x) < TOL and re.match(r'^\d{1,4}$', txt):
                        long_val = txt

                    # Short : x≈short_x + petit nombre
                    elif abs(x - short_x) < TOL and re.match(r'^\d{1,4}$', txt):
                        short_val = txt

                    # Contract : x >= contract_x (tout ce qui suit)
                    elif contract_x and x >= contract_x - TOL:
                        # Garder seulement texte contract, pas prix/débit
                        if re.match(r'^[A-Z0-9\-\.]+$', txt) and not re.match(r'^\d{2,}[\.,]\d+', txt):
                            contract_parts.append(txt)

                if not trade_date or (not long_val and not short_val):
                    continue

                # Parser contract : "06 MAR 26 EUR EUR-BUND" → Mon=MAR Yr=26 Product=EUR-BUND
                contract_str = " ".join(contract_parts)
                mc = re.search(r'([A-Z]{3})\s+(\d{2})\s+(?:\w+\s+)?(.+)', contract_str)
                if mc:
                    mon     = mc.group(1)
                    yr      = mc.group(2)
                    product = mc.group(3).strip()
                else:
                    product = contract_str

                # CCY : dernier mot 2 lettres avant fin
                ccy_match = re.search(r'\b([A-Z]{2})\b', contract_str)
                ccy = ccy_match.group(1) if ccy_match else ""

                ligne_data = {
                    "Trade Date": trade_date,
                    "Long":       long_val,
                    "Short":      short_val,
                    "Product":    product,
                    "Mon":        mon,
                    "Yr":         yr,
                    "CCY":        ccy,
                }
                toutes_les_lignes.append(ligne_data)
                print(f"  ✅ {trade_date} | Long={long_val} | Short={short_val} | {product} {mon} {yr}")

    print(f"\n📊 BAML - Total lignes : {len(toutes_les_lignes)}")
    return toutes_les_lignes

def formater_output(lignes):
    df = pd.DataFrame(lignes)
    if df.empty:
        return df

    df["Long"]  = pd.to_numeric(df["Long"],  errors="coerce").fillna(0).astype(int)
    df["Short"] = pd.to_numeric(df["Short"], errors="coerce").fillna(0).astype(int)

    resume = df.groupby(["Product", "CCY", "Mon", "Yr"], as_index=False).agg(
        Total_Long =("Long",  "sum"),
        Total_Short=("Short", "sum")
    )
    resume["Total_Long"]  = resume["Total_Long"].replace(0, "")
    resume["Total_Short"] = resume["Total_Short"].replace(0, "")
    return resume[["Product", "Total_Long", "Total_Short", "CCY", "Mon", "Yr"]]
