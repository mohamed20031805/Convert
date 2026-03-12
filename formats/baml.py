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
                    if l and not any(x in l for x in ["CABOT","LONDON","UNITED","PAGE"]):
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


def get_col_positions(header_ligne):
    cols = {}
    for col in ["TRADE", "LONG", "SHORT", "CONTRACT", "CC"]:
        idx = header_ligne.find(col)
        if idx >= 0:
            cols[col] = idx
    return cols


def extraire_positions(chemin_pdf):
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text()
            if not texte:
                continue

            lignes = texte.split('\n')

            # Chercher header
            header_idx = None
            cols = {}
            for j, ligne in enumerate(lignes):
                if ("LONG" in ligne and "SHORT" in ligne
                        and "TRADE" in ligne and "CONTRACT" in ligne):
                    cols = get_col_positions(ligne)
                    header_idx = j
                    print(f"\n✅ Page {i+1} - cols={cols}")
                    break

            if not cols or header_idx is None:
                continue

            p_trade    = cols.get("TRADE",    0)
            p_long     = cols.get("LONG",     15)
            p_short    = cols.get("SHORT",    20)
            p_contract = cols.get("CONTRACT", 26)
            p_cc       = cols.get("CC",       56)
            p_contract_end = p_cc - 3

            last_contract   = ""
            last_trade_date = ""
            last_cc         = ""

            for ligne in lignes[header_idx + 2:]:

                if any(x in ligne for x in [
                    "AVG ", "PAGE", "MERRILL", "FUTURES", "KING",
                    "LONDON", "MORGAN", "FUND", "FCH", "CABOT", "UNITED",
                    "KINGDOM", "CONFIRMATION", "ACCEPTED", "PURCHASE",
                    "SALE", "SETTL AT", "COMMISSION", "NET PROFIT",
                    "GROSS", "CLEARING", "BROKERAGE", "OPEN TRADE",
                    "* REG", "* SEC", "OPTION PREMIUM"
                ]):
                    continue

                stripped = ligne.strip()
                if not stripped:
                    continue

                # ── Ligne TOTAL : N* ──
                total_m = re.match(r'^([\d,]+)\*', stripped)
                if total_m:
                    val = total_m.group(1).replace(',', '')

                    # Position du * dans la ligne originale
                    pos_star = len(ligne) - len(ligne.lstrip()) + len(total_m.group(1))
                    long_val  = ""
                    short_val = ""
                    dist_long  = abs(pos_star - (p_long  + len(total_m.group(1))))
                    dist_short = abs(pos_star - (p_short + len(total_m.group(1))))
                    if dist_long <= dist_short:
                        long_val  = val
                    else:
                        short_val = val

                    # Parser contract
                    mon = yr = product = ccy = ""
                    mc = re.search(
                        r'\d{2}\s+([A-Z]{3})\s+(\d{2})\s+(?:([A-Z]{2,3})\s+)?(.+)',
                        last_contract
                    )
                    if mc:
                        mon     = mc.group(1)
                        yr      = mc.group(2)
                        ccy     = last_cc or mc.group(3) or ""
                        product = mc.group(4).strip()
                    else:
                        mc2 = re.search(
                            r'([A-Z]{3})\s+(\d{2})\s+(?:([A-Z]{2,3})\s+)?(.+)',
                            last_contract
                        )
                        if mc2:
                            mon     = mc2.group(1)
                            yr      = mc2.group(2)
                            ccy     = last_cc or mc2.group(3) or ""
                            product = mc2.group(4).strip()
                        else:
                            product = last_contract
                            ccy     = last_cc

                    if not product:
                        continue

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
                    print(f"  ✅ {last_trade_date} | L={long_val} | S={short_val} | {product} {mon} {yr} {ccy}")
                    continue

                # Ignorer CLOSE
                if stripped.startswith("CLOSE"):
                    continue

                # ── Ligne de données ──
                if len(ligne) < p_contract:
                    continue

                trade_date = ligne[p_trade : p_trade + 8].strip()
                contract   = ligne[p_contract : p_contract_end].strip() if len(ligne) > p_contract else ""
                cc         = ligne[p_cc : p_cc + 3].strip() if len(ligne) > p_cc else ""

                # Ligne avec date + contract
                if re.match(r'^\d{1,2}/\d{1,2}/\d{1,2}$', trade_date) and contract:
                    last_trade_date = trade_date
                    last_contract   = contract
                    last_cc         = cc if re.match(r'^[A-Z]{2}$', cc) else last_cc
                    continue

                # Ligne de continuation (contract sur 2 lignes)
                if not trade_date and contract and len(stripped) > 3:
                    last_contract = (last_contract + " " + contract).strip()

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
