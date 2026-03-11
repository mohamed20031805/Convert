import pdfplumber
import re
import pandas as pd

def detecter(texte):
    return "MERRILL LYNCH INTERNATIONAL" in texte

def extraire_entete(chemin_pdf, template_json=None):
    infos = {
        "Broker":           "MERRILL LYNCH INTERNATIONAL",
        "Client":           "",
        "Account":          "",
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

        # Client : lignes entre adresse broker et adresse client
        lignes = texte.split('\n')
        for i, ligne in enumerate(lignes):
            if "MORGAN STANLY" in ligne or "MORGAN STANLEY" in ligne:
                client_parts = []
                for j in range(i, min(i+4, len(lignes))):
                    l = lignes[j].strip()
                    if l and not any(x in l for x in ["CABOT", "LONDON", "UNITED", "PAGE"]):
                        client_parts.append(l)
                infos["Client"] = " ".join(client_parts)
                break

    if template_json:
        import json, os
        if os.path.exists(template_json):
            with open(template_json) as f:
                t = json.load(f)
            for k, v in t.items():
                if not infos.get(k):
                    infos[k] = v

    print(f"✅ Entête BAML : {infos}")
    return infos

def extraire_positions(chemin_pdf):
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text() or ""

            # Pages avec LONG SHORT dans l'entête
            if "LONG" not in texte or "SHORT" not in texte:
                continue
            if "CONTRACT DESCRIPTION" not in texte:
                continue

            print(f"\n✅ Page {i+1} - données BAML")

            lignes = texte.split('\n')
            dans_bloc = False

            for ligne in lignes:
                ligne = ligne.strip()

                # Début bloc : ligne entête colonnes
                if re.match(r'^TRADE\s+SETTL\s+AT\s+LONG', ligne):
                    dans_bloc = True
                    continue

                if not dans_bloc:
                    continue

                # Ignorer séparateurs, totaux, AVG, CLOSE, vides
                if not ligne:
                    continue
                if re.match(r'^-+', ligne):
                    continue
                if any(x in ligne for x in [
                    "AVG", "CLOSE", "TOTAL", "COMMISSION", "BROKERAGE",
                    "NET PROFIT", "GROSS PROFIT", "CLEARING", "PAGE",
                    "MERRILL", "FUTURES", "KING", "LONDON", "MORGAN",
                    "FUND", "FCH", "CABOT", "UNITED", "KINGDOM",
                    "PURCHASE", "SALE", "CONFIRMATION", "ACCEPTED"
                ]):
                    continue

                # Ligne de données : commence par une date MM/DD/Y ou MM/DD/YY
                m = re.match(
                    r'^(\d{1,2}/\d{1,2}/\d{1,2})\s+'   # Trade Date
                    r'(\w+)\s+'                           # SETTL
                    r'(\w+)\s+'                           # AT
                    r'(\d+)?\s*'                          # LONG (optionnel)
                    r'(\d+)?\s*'                          # SHORT (optionnel)
                    r'(.+?)\s+'                           # CONTRACT DESCRIPTION
                    r'(\d+)\s+'                           # EX
                    r'([\d.,]+)\s+'                       # PRICE
                    r'(\w+)',                             # CC
                    ligne
                )

                if not m:
                    continue

                trade_date   = m.group(1)
                long_val     = m.group(4) or ""
                short_val    = m.group(5) or ""
                contract     = m.group(6).strip()
                ccy          = m.group(9).strip()

                # Parser contract : "06 MAR 26 EUR EUR-BUND" → Product=EUR-BUND, Mon=MAR, Yr=26
                mon = yr = product = ""
                mc = re.search(r'(\w{3})\s+(\d{2})\s+(?:\w+\s+)?(.+)', contract)
                if mc:
                    mon     = mc.group(1)
                    yr      = mc.group(2)
                    product = mc.group(3).strip()

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
                print(f"  ✅ {trade_date} | Long={long_val} | Short={short_val} | {product} {mon} {yr} {ccy}")

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
