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
            for j, ligne in enumerate(lignes):
                if ("LONG" in ligne and "SHORT" in ligne
                        and "TRADE" in ligne and "CONTRACT" in ligne):
                    header_idx = j
                    print(f"\n✅ Page {i+1}")
                    break

            if header_idx is None:
                continue

            last_contract   = ""
            last_trade_date = ""
            last_cc         = ""
            pending_total   = None

            data_lignes = lignes[header_idx + 2:]

            for ligne in data_lignes:
                stripped = ligne.strip()
                if not stripped:
                    continue

                # ── AVG LONG / AVG SHORT → résoudre Long ou Short ──
                if stripped.startswith("AVG LONG:") or stripped.startswith("AVG SHORT:"):
                    if pending_total:
                        val = pending_total["val"]
                        if "LONG" in stripped:
                            long_val  = val
                            short_val = ""
                        else:
                            long_val  = ""
                            short_val = val

                        ligne_data = {
                            "Trade Date": last_trade_date,
                            "Long":       long_val,
                            "Short":      short_val,
                            "Product":    pending_total["product"],
                            "Mon":        pending_total["mon"],
                            "Yr":         pending_total["yr"],
                            "CCY":        pending_total["ccy"],
                        }
                        toutes_les_lignes.append(ligne_data)
                        print(f"  ✅ {last_trade_date} | L={long_val} | S={short_val} | {pending_total['product']} {pending_total['mon']} {pending_total['yr']} {pending_total['ccy']}")
                        pending_total = None
                    continue

                # ── Ligne TOTAL : commence par N* ──
                if re.match(r'^[\d,\.]+\*', stripped):
                    # Ignorer COMMISSION, GROSS, CONVERTED etc
                    if any(x in stripped for x in [
                        "COMMISSION", "GROSS", "CONVERTED", "NET PROFIT", "SEC"
                    ]):
                        continue

                    total_m = re.match(r'^([\d,\.]+)\*', stripped)
                    if not total_m:
                        continue
                    val = total_m.group(1).replace(',', '').replace('.', '')

                    # ── Contract TEL QUEL ──
                    mon = yr = ""
                    mc = re.search(r'([A-Z]{3})\s+(\d{2})\b', last_contract)
                    if mc:
                        mon = mc.group(1)
                        yr  = mc.group(2)
                    ccy     = last_cc
                    product = last_contract  # TEL QUEL

                    if not product:
                        continue

                    # Cas 1 : "N* CLOSE ..." sans EX → attendre AVG LONG/SHORT
                    if "CLOSE" in stripped and "EX" not in stripped:
                        pending_total = {
                            "val":     val,
                            "product": product,
                            "mon":     mon,
                            "yr":      yr,
                            "ccy":     ccy,
                        }

                    # Cas 2 : "N* EX-... CLOSE ..." → Long par défaut
                    elif "EX" in stripped and "CLOSE" in stripped:
                        ligne_data = {
                            "Trade Date": last_trade_date,
                            "Long":       val,
                            "Short":      "",
                            "Product":    product,
                            "Mon":        mon,
                            "Yr":         yr,
                            "CCY":        ccy,
                        }
                        toutes_les_lignes.append(ligne_data)
                        print(f"  ✅ {last_trade_date} | L={val} | S= | {product} {mon} {yr} {ccy}")

                    continue

                # Ignorer lignes système
                if any(x in ligne for x in [
                    "PAGE", "MERRILL", "FUTURES", "KING", "LONDON",
                    "MORGAN", "FUND", "FCH", "CABOT", "UNITED", "KINGDOM",
                    "CONFIRMATION", "ACCEPTED", "PURCHASE", "SALE",
                    "COMMISSION", "NET PROFIT", "GROSS", "CLEARING",
                    "BROKERAGE", "OPEN TRADE", "* REG", "* SEC",
                    "OPTION", "CONVERTED", "CLOSE", "------",
                    "TRADING UNIT"
                ]):
                    continue

                # ── Ligne de données : date + contract + CC ──
                m = re.match(
                    r'^(\d{1,2}/\d{1,2}/\d{1,2})\s+'  # date
                    r'\w+\s+'                            # SETTL
                    r'\w+\s+'                            # AT
                    r'[\d,]+\s+'                         # quantité
                    r'(.+?)\s+'                          # contract description TEL QUEL
                    r'\d+\s+'                            # EX
                    r'[\d\.\-]+\s+'                      # PRICE
                    r'([A-Z]{2})\s*',                   # CC
                    stripped
                )
                if m:
                    last_trade_date = m.group(1)
                    last_contract   = m.group(2).strip()
                    last_cc         = m.group(3).strip()

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
