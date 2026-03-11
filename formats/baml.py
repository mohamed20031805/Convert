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
                for j in range(i, min(i + 4, len(lignes))):
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

            # Chercher entête LONG/SHORT
            long_x = short_x = trade_x = contract_x = header_y = None
            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]
                texte_ligne = " ".join(w['text'] for w in mots)
                if ("LONG" in texte_ligne and "SHORT" in texte_ligne
                        and "TRADE" in texte_ligne and "CONTRACT" in texte_ligne):
                    for w in mots:
                        if w['text'] == "TRADE":    trade_x    = w['x0']
                        if w['text'] == "LONG":     long_x     = w['x0']
                        if w['text'] == "SHORT":    short_x    = w['x0']
                        if w['text'] == "CONTRACT": contract_x = w['x0']
                    header_y = y
                    print(f"\n✅ Page {i+1} - LONG x={long_x:.1f} SHORT x={short_x:.1f} CONTRACT x={contract_x:.1f}")
                    break

            if not long_x or not header_y:
                continue

            TOL = 25
            ys_sorted = [y for y in sorted(lignes_mots.keys()) if y > header_y]

            last_contract   = ""
            last_trade_date = ""

            for y in ys_sorted:
                mots = lignes_mots[y]
                texte_ligne = " ".join(w['text'] for w in mots)

                # Ignorer lignes système
                if any(x in texte_ligne for x in [
                    "AVG ", "PAGE", "MERRILL", "FUTURES", "KING",
                    "LONDON", "MORGAN", "FUND", "FCH", "CABOT", "UNITED",
                    "KINGDOM", "CONFIRMATION", "ACCEPTED", "PURCHASE",
                    "SALE", "------", "SETTL", "DEBIT", "COMMISSION",
                    "NET PROFIT", "GROSS", "CLEARING", "BROKERAGE",
                    "OPEN TRADE", "OPTION"
                ]):
                    continue

                # Mémoriser Trade Date
                for w in mots:
                    if abs(w['x0'] - trade_x) < TOL and re.match(r'^\d{1,2}/\d{1,2}/\d{1,2}$', w['text']):
                        last_trade_date = w['text']

                # ── Ligne TOTAL : contient N* (avec ou sans virgule) ──
                total_match = re.search(r'\b[\d,]+\*', texte_ligne)
                if total_match:
                    long_val  = ""
                    short_val = ""

                    for w in mots:
                        if re.match(r'^[\d,]+\*$', w['text']):
                            val = w['text'].replace('*', '').replace(',', '')
                            dist_long  = abs(w['x0'] - long_x)
                            dist_short = abs(w['x0'] - short_x)
                            if dist_long < dist_short:
                                long_val  = val
                            else:
                                short_val = val

                    if not long_val and not short_val:
                        continue

                    # Parser contract
                    mon = yr = product = ccy = ""

                    # Format "06 MAR 26 EUR EUR-BUND"
                    mc = re.search(
                        r'\d{2}\s+([A-Z]{3})\s+(\d{2})\s+(?:([A-Z]{2,3})\s+)?(.+)',
                        last_contract
                    )
                    if mc:
                        mon     = mc.group(1)
                        yr      = mc.group(2)
                        ccy     = mc.group(3) or ""
                        product = mc.group(4).strip()
                    else:
                        # Format "MAR 26 CBT ULT TNOTE" ou "MAR 26 EURO-BTP"
                        mc2 = re.search(
                            r'([A-Z]{3})\s+(\d{2})\s+(?:([A-Z]{2,3})\s+)?(.+)',
                            last_contract
                        )
                        if mc2:
                            mon     = mc2.group(1)
                            yr      = mc2.group(2)
                            ccy     = mc2.group(3) or ""
                            product = mc2.group(4).strip()
                        else:
                            product = last_contract

                    ligne_data = {
                        "Trade Date": last_trade_date,
                        "Long":       long_val,
                        "Short":      short_val,
                        "Product":    product,
                        "Mon":        mon,
                        "Yr":         yr,
                        "CCY":        ccy,
                    }
                    toutes_les_lignes.append(ligne_data)
                    print(f"  ✅ {last_trade_date} | Long={long_val} | Short={short_val} | {product} {mon} {yr} {ccy}")
                    continue

                # ── Ligne de données : mémoriser contract ──
                contract_parts = []
                for w in mots:
                    if w['x0'] >= contract_x - TOL:
                        txt = w['text']
                        # Arrêter au EX (nombre 2 chiffres ex: 27) ou prix décimal
                        if re.match(r'^\d{3,}[\.,]', txt):
                            break
                        if re.match(r'^\d{2}$', txt) and int(txt) > 26:
                            break
                        contract_parts.append(txt)

                if contract_parts:
                    last_contract = " ".join(contract_parts).strip()

    print(f"\n📊 BAML - Total : {len(toutes_les_lignes)} positions")
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
