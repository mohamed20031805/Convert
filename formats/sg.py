import pdfplumber
import re
import pandas as pd
import json
import os


def detecter(texte):
    return "SOCIETE GENERALE" in texte and "Detailed Statements" in texte


def extraire_entete(chemin_pdf, template_json=None):
    infos = {
        "Broker":            "SOCIETE GENERALE",
        "Client":            "",
        "Account":           "",
        "Close of Business": ""
    }
    with pdfplumber.open(chemin_pdf) as pdf:
        texte = pdf.pages[0].extract_text() or ""
        for ligne in texte.split('\n'):
            m = re.search(r'ACCOUNT NUMBER\s*:\s*(.+)', ligne)
            if m and not infos["Account"]:
                infos["Account"] = m.group(1).strip()
            m = re.search(r'STATEMENT DATE\s*:\s*(.+)', ligne)
            if m and not infos["Close of Business"]:
                infos["Close of Business"] = m.group(1).strip()

        # Client = lignes après adresse SG, avant ATTN
        lignes = texte.split('\n')
        client_parts = []
        capture = False
        for ligne in lignes:
            l = ligne.strip()
            if "PARIS LA DEFENSE" in l or "COURS VALMY" in l:
                capture = True
                continue
            if capture:
                if "ATTN" in l or "SWITZERLAND" in l or "LUXEMBOURG" in l:
                    break
                if l and not any(x in l for x in [
                    "SOCIETE", "TOUR", "17,", "92987", "VIA", "69000",
                    "5 ALLEE", "L-2520", "L 2520"
                ]):
                    client_parts.append(l)
        infos["Client"] = " - ".join([p for p in client_parts if p])

    if template_json and os.path.exists(template_json):
        with open(template_json) as f:
            t = json.load(f)
        for k, v in t.items():
            if not infos.get(k):
                infos[k] = v

    print(f"✅ Entête SG : {infos}")
    return infos


def extraire_positions(chemin_pdf, account_number=None):
    toutes_les_lignes = []

    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text()
            if not texte:
                continue

            lignes = texte.split('\n')

            # ── Détecter account sur cette page ──
            current_account = ""
            for ligne in lignes:
                m = re.search(r'ACCOUNT NUMBER\s*:\s*(.+)', ligne)
                if m:
                    current_account = m.group(1).strip()
                    break

            # ── Filtrer par account si fourni ──
            if account_number and current_account:
                if account_number not in current_account:
                    continue

            # ── Chercher section OPEN POSITIONS ──
            header_idx = None
            for j, ligne in enumerate(lignes):
                if ("LONG" in ligne and "SHORT" in ligne
                        and "TRADE" in ligne and "CONTRACT" in ligne):
                    header_idx = j
                    print(f"\n✅ Page {i+1} - OPEN POSITIONS trouvé")
                    break

            if header_idx is None:
                continue

            last_contract   = ""
            last_trade_date = ""
            last_cc         = ""
            pending_total   = None

            for ligne in lignes[header_idx + 2:]:
                stripped = ligne.strip()
                if not stripped:
                    continue

                # ── Stop si fin de section ──
                if any(x in ligne for x in [
                    "BEGINNING ACCOUNT", "CASH JOURNALS",
                    "ENDING ACCOUNT", "LME TRADES", "DERIVATIVE"
                ]):
                    break

                # ── AVG LONG / AVG SHORT ──
                if stripped.startswith("AVG LONG:") or stripped.startswith("AVG SHORT:"):
                    if pending_total:
                        long_val  = pending_total["val"] if "LONG"  in stripped else ""
                        short_val = pending_total["val"] if "SHORT" in stripped else ""
                        toutes_les_lignes.append({
                            "Trade Date": last_trade_date,
                            "Long":       long_val,
                            "Short":      short_val,
                            "Product":    pending_total["product"],
                            "Mon":        pending_total["mon"],
                            "Yr":         pending_total["yr"],
                            "CCY":        pending_total["ccy"],
                        })
                        print(f"  ✅ {last_trade_date} | L={long_val} | S={short_val} | {pending_total['product']}")
                        pending_total = None
                    last_contract = ""
                    continue

                # ── Ligne TOTAL : N* CLOSE ──
                if re.match(r'^[\d,]+\*', stripped) and "CLOSE" in stripped:
                    total_m = re.match(r'^([\d,]+)\*', stripped)
                    if not total_m or not last_contract:
                        continue

                    val = total_m.group(1).replace(',', '')

                    mon = yr = ""
                    mc = re.search(r'([A-Z]{3})\s+(\d{2})\b', last_contract)
                    if mc:
                        mon = mc.group(1)
                        yr  = mc.group(2)

                    pending_total = {
                        "val":     val,
                        "product": last_contract,
                        "mon":     mon,
                        "yr":      yr,
                        "ccy":     last_cc,
                    }
                    continue

                # ── Ignorer lignes système ──
                if any(x in ligne for x in [
                    "------", "* * *", "** US", "** SWISS",
                    "** EURO", "** JAPANESE", "** BRITISH",
                    "TOTAL CONVERTED", "FUNDS PAID",
                    "O P E N", "C O N F"
                ]):
                    continue

                # ── Ligne de données ──
                # "10DEC25 10DEC25 US 42 MAR 26 IMM EURO FX 16 1.169450 US 104,212.50"
                m = re.match(
                    r'^(\w+)\s+'          # TRADE DATE
                    r'\w+\s+'             # SETTL
                    r'\w+\s+'             # AT
                    r'([\d,]+)\s+'        # LONG ou SHORT
                    r'(.+?)\s+'           # CONTRACT
                    r'\d+\s+'             # EX
                    r'[\d\.]+\s+'         # PRICE
                    r'([A-Z]{2})\s+',     # CC
                    stripped
                )
                if m:
                    last_trade_date = m.group(1)
                    qty             = m.group(2).replace(',', '')
                    last_contract   = m.group(3).strip()
                    last_cc         = m.group(4).strip()
                    continue

                # ── Ligne SHORT : quantité dans colonne SHORT ──
                # Détecter si la quantité vient avant le contract (Long)
                # ou si c'est un SHORT (pas de Long sur la ligne)

    print(f"\n📊 SG - Total : {len(toutes_les_lignes)} positions")
    return toutes_les_lignes


def formater_output(lignes):
    df = pd.DataFrame(lignes)
    if df.empty:
        return pd.DataFrame(columns=[
            "Trade Date", "Long", "Short", "Product", "Mon", "Yr", "CCY"
        ])
    df["Long"]  = pd.to_numeric(df["Long"],  errors="coerce").fillna(0).astype(int)
    df["Short"] = pd.to_numeric(df["Short"], errors="coerce").fillna(0).astype(int)
    df["Long"]  = df["Long"].replace(0,  "")
    df["Short"] = df["Short"].replace(0, "")
    return df[["Trade Date", "Long", "Short", "Product", "Mon", "Yr", "CCY"]]
