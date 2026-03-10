import pdfplumber
import re

def extraire_open_positions(chemin_pdf):
    toutes_les_lignes = []
    
    with pdfplumber.open(chemin_pdf) as pdf:
        for i, page in enumerate(pdf.pages):
            texte = page.extract_text()
            if not texte or "OPEN POSITIONS" not in texte:
                continue

            # ── 1. Trouver positions X de Long et Short via extract_words ──
            col_long_x  = None
            col_short_x = None
            words = page.extract_words()
            for w in words:
                if w['text'] == 'Long'  and col_long_x  is None:
                    col_long_x  = w['x0']
                if w['text'] == 'Short' and col_short_x is None:
                    col_short_x = w['x0']

            if not col_long_x or not col_short_x:
                continue

            # ── 2. Regrouper les mots par ligne (coordonnée Y) ──
            lignes_mots = {}
            for w in words:
                y = round(w['top'], 0)
                if y not in lignes_mots:
                    lignes_mots[y] = []
                lignes_mots[y].append(w)

            # ── 3. Parcourir les lignes du texte brut ──
            lignes_texte = texte.split("\n")
            dans_bloc = False
            # Index pour relier texte brut ↔ mots avec positions
            lignes_dates = {}  # date+ref → long/short

            # D'abord, calculer Long/Short pour chaque ligne de données
            for y in sorted(lignes_mots.keys()):
                mots = lignes_mots[y]
                premier = mots[0]['text']
                if not re.match(r'^\d{2}[A-Z]{3}\d{2}$', premier):
                    continue
                # Ignorer si c'est une ligne de TRADE ACTIVITY (a un Trade Code court au milieu)
                texte_ligne = " ".join(w['text'] for w in mots)
                
                long_val  = ""
                short_val = ""
                if len(mots) > 1:
                    qte_mot = mots[1]
                    if re.match(r'^\d+$', qte_mot['text']):
                        dist_long  = abs(qte_mot['x0'] - col_long_x)
                        dist_short = abs(qte_mot['x0'] - col_short_x)
                        if dist_long < dist_short:
                            long_val  = qte_mot['text']
                        else:
                            short_val = qte_mot['text']
                
                # Clé = Trade Date + Trade Ref (dernier mot)
                trade_ref = mots[-1]['text']
                cle = f"{premier}_{trade_ref}"
                lignes_dates[cle] = (long_val, short_val)

            # ── 4. Parser le texte brut ligne par ligne ──
            for ligne in lignes_texte:
                ligne = ligne.strip()

                # Détecter début du bloc OPEN POSITIONS
                if re.match(r'^Date\s+Call\s+Price\s+Ref', ligne):
                    dans_bloc = True
                    continue

                if not dans_bloc:
                    continue

                if any(mot in ligne for mot in [
                    "OPEN POSITIONS", "No open positions", "Continuation",
                    "Account", "Close of Business", "Average", "Settlement", "Totals"
                ]):
                    continue

                if not re.match(r'^\d{2}[A-Z]{3}\d{2}', ligne):
                    continue

                # ── 5. Parser la ligne ──
                parsed = parser_ligne(ligne)
                if not parsed:
                    continue

                # ── 6. Retrouver Long/Short via la clé ──
                cle = f"{parsed['Trade Date']}_{parsed['Trade Ref']}"
                long_val, short_val = lignes_dates.get(cle, ("", ""))
                parsed["Long"]  = long_val
                parsed["Short"] = short_val

                toutes_les_lignes.append(parsed)
                print(f"  ✅ {parsed}")

    print(f"\n📊 Total lignes extraites : {len(toutes_les_lignes)}")
    return toutes_les_lignes


def parser_ligne(ligne):
    # Ancrer depuis la fin : Market Value + CCY + Trade Ref
    fin = re.compile(
        r'^(.+?)\s+([-\d,]+\.\d+)\s+([A-Z]{3})\s+([A-Z0-9]+)$'
    )
    m = fin.match(ligne)
    if not m:
        # Essayer sans CCY (certaines lignes l'omettent)
        fin2 = re.compile(
            r'^(.+?)\s+([-\d,]+\.\d+)\s+([A-Z0-9]+)$'
        )
        m = fin2.match(ligne)
        if not m:
            print(f"  ⚠️  Non parsé (fin) : '{ligne}'")
            return None
        debut     = m.group(1).strip()
        mkt_value = m.group(2)
        ccy       = ""
        trade_ref = m.group(3)
    else:
        debut     = m.group(1).strip()
        mkt_value = m.group(2)
        ccy       = m.group(3)
        trade_ref = m.group(4)

    # Parser le début : Date + Qte + Exch + reste
    debut_p = re.compile(
        r'^(\d{2}[A-Z]{3}\d{2})\s+(\d+)\s+([A-Z]{2,4})\s+(.+)$'
    )
    m2 = debut_p.match(debut)
    if not m2:
        print(f"  ⚠️  Non parsé (début) : '{debut}'")
        return None

    trade_date = m2.group(1)
    exch       = m2.group(3)
    milieu     = m2.group(4).strip()

    # Parser le milieu : Product + Mon + Yr + [Strike] + [Put/Call]
    milieu_p = re.compile(
        r'^(.+?)\s+([A-Z]{3})\s+(\d{2})'       # Product Mon Yr
        r'(?:\s+([\d.V]+[A-Z0-9]*))?'           # Strike optionnel
        r'(?:\s+([A-Z]+))?$'                    # Put/Call optionnel
    )
    m3 = milieu_p.match(milieu)
    if not m3:
        print(f"  ⚠️  Non parsé (milieu) : '{milieu}'")
        return None

    return {
        "Trade Date":   trade_date,
        "Long":         "",   # rempli après
        "Short":        "",   # rempli après
        "Exch":         exch,
        "Product":      m3.group(1).strip(),
        "Mon":          m3.group(2),
        "Yr":           m3.group(3),
        "Strike":       m3.group(4) or "",
        "Put/Call":     m3.group(5) or "",
        "Market Value": mkt_value,
        "CCY":          ccy,
        "Trade Ref":    trade_ref,
    }
# Remplacez par votre nom de fichier
#lignes = extraire_open_positions("pdfs/open_positions_morgan_stanley.pdf")
def extraire_entete(chemin_pdf, template_json=None):
    """
    Extrait les 4 éléments clés de l'entête :
    1. Courtier (ex: MORGAN STANLEY & CO. LLC)
    2. Client   (ex: 20UGS (UCITS) FUNDS TCW UNCONSTRAINED... - 3757)
    3. Close of Business
    4. Account
    """
    with pdfplumber.open(chemin_pdf) as pdf:
        page = pdf.pages[0]
        lignes = page.extract_text().split("\n")

    infos = {
        "Broker":            "",
        "Client":            "",
        "Close of Business": "",
        "Account":           ""
    }

    # Sections qui marquent la fin de l'entête
    fin_entete = [
        "TRADE ACTIVITY", "OPEN POSITIONS",
        "CASH TRANSACTIONS", "FUTURES CONFIRMATIONS"
    ]

    lignes_entete = []
    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne:
            continue
        if any(s in ligne for s in fin_entete):
            break
        lignes_entete.append(ligne)

    print(f"\n📋 Lignes entête brutes :")
    for i, l in enumerate(lignes_entete):
        print(f"  [{i}] '{l}'")

    for i, ligne in enumerate(lignes_entete):

        # ── Account ──
        m = re.search(r'Account\s+([A-Z0-9]+\s*/\s*[A-Z0-9]+)', ligne)
        if m and not infos["Account"]:
            infos["Account"] = m.group(1).strip()

        # ── Close of Business ──
        m = re.search(r'Close of Business\s+(.+)', ligne)
        if m and not infos["Close of Business"]:
            infos["Close of Business"] = m.group(1).strip()

        # ── Broker : ligne qui contient "&" ou "LLC" ou "LTD" ou "INC" ──
        if not infos["Broker"]:
            if re.search(r'\b(LLC|LTD|INC|CO\.|CORP|BANK|SECURITIES)\b', ligne, re.IGNORECASE):
                infos["Broker"] = ligne

        # ── Client : ligne qui contient un numéro de stratégie (- XXXX) ──
        # Format : "NOM FONDS ... - 3757"
        if not infos["Client"]:
            m = re.search(r'(.+?-\s*\d{3,6})', ligne)
            if m:
                # Construire le nom complet du client (peut être sur 2 lignes)
                client_parts = [ligne]
                # Regarder la ligne suivante si elle continue la description
                if i + 1 < len(lignes_entete):
                    next_ligne = lignes_entete[i + 1]
                    # Si la ligne suivante n'a pas de mots-clés connus
                    if not re.search(r'(Close|Account|LLC|LTD|Street|Avenue)', next_ligne, re.IGNORECASE):
                        client_parts.append(next_ligne)
                infos["Client"] = " ".join(client_parts).strip()

    print(f"\n✅ Infos extraites :")
    for k, v in infos.items():
        print(f"   {k:20} : {v}")

    return infos



# def diagnostic_triton(chemin_pdf):
#     with pdfplumber.open(chemin_pdf) as pdf:
#         page = pdf.pages[0]
#         print("=== TEXTE BRUT ===")
#         lignes = page.extract_text().split("\n")
#         for i, l in enumerate(lignes):
#             print(f"[{i}] '{l}'")
        
#         print("\n=== TABLEAUX ===")
#         tables = page.extract_tables()
#         print(f"{len(tables)} tableau(x) détecté(s)")
#         for j, t in enumerate(tables):
#             print(f"\nTableau {j+1}:")
#             for ligne in t:
#                 print(ligne)

# diagnostic_triton("pdfs/Athens_Derivatives_Statement.pdf")
def extraire_entete_triton(chemin_pdf):
    """Entête spécifique au format Triton / Athens Derivatives"""
    with pdfplumber.open(chemin_pdf) as pdf:
        lignes = pdf.pages[0].extract_text().split("\n")

    infos = {
        "Broker":            "",
        "Client":            "",
        "Close of Business": "",
        "Account":           ""
    }

    for ligne in lignes:
        ligne = ligne.strip()

        # Client : première ligne du PDF
        if not infos["Client"] and re.match(r'^[A-Z]', ligne):
            if "STATEMENT" not in ligne and "Athens" not in ligne:
                infos["Client"] = ligne

        # Account : "ACCOUNT : XXXXXXX"
        m = re.search(r'ACCOUNT\s*:\s*(\S+)', ligne)
        if m and not infos["Account"]:
            infos["Account"] = m.group(1).strip()

        # Date : "ATHENS , 30/01/26"
        m = re.search(r'ATHENS\s*,\s*(\d{2}/\d{2}/\d{2})', ligne)
        if m and not infos["Close of Business"]:
            infos["Close of Business"] = m.group(1).strip()

        # Broker : "Athens Derivatives EXchange"
        if "Derivatives" in ligne and not infos["Broker"]:
            infos["Broker"] = ligne.strip()

    print(f"\n✅ Entête Triton :")
    for k, v in infos.items():
        print(f"   {k:20} : {v}")

    return infos


def extraire_open_positions_triton(chemin_pdf):
    """
    Extraction OPEN POSITIONS pour le format Triton.
    Utilise extract_tables() car le tableau est bien structuré.
    On extrait : Trade Date, Trade Number, Long, Short
    On propage : Contract (Product), Maturity (Mon+Yr)
    """
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

                # Vérifier que c'est bien le tableau OPEN POSITIONS
                headers = [str(h).replace("\n", " ") if h else "" for h in table[0]]
                if "TRADE" not in " ".join(headers) and "LONG" not in " ".join(headers):
                    continue

                print(f"\n✅ Tableau OPEN POSITIONS trouvé - Page {i+1}")
                print(f"   Colonnes : {headers}")

                # Indices des colonnes
                # CONTRACT=0, MATURITY=1, SETTLEMENT=2, TRADE DATE=3,
                # TRADE NUMBER=4, LONG=5, SHORT=6
                current_contract = ""
                current_maturity = ""

                for row in table[1:]:  # Ignorer l'entête
                    if not row or not any(row):
                        continue

                    # Ignorer les lignes TOTAL
                    row_text = " ".join(str(c) for c in row if c)
                    if "TOTAL" in row_text:
                        continue

                    # Propager Contract si présent
                    if row[0] and row[0].strip():
                        current_contract = row[0].strip()

                    # Propager Maturity si présent
                    if row[1] and row[1].strip():
                        current_maturity = row[1].strip()
                        # Ex: "FEB 2026 20/02/26" → Mon=FEB, Yr=2026
                    
                    # Parser Mon et Yr depuis la maturité
                    mon = ""
                    yr  = ""
                    if current_maturity:
                        m = re.match(r'([A-Z]+)\s+(\d{4})', current_maturity)
                        if m:
                            mon = m.group(1)
                            yr  = m.group(2)

                    # Trade Date (col 3)
                    trade_date    = row[3].strip() if row[3] else ""
                    trade_number  = row[4].strip() if row[4] else ""
                    long_val      = row[5].strip() if row[5] else ""
                    short_val     = row[6].strip() if row[6] else ""

                    # Ignorer les lignes sans date valide
                    if not re.match(r'\d{2}/\d{2}/\d{2}', trade_date):
                        continue

                    # Ignorer les lignes sans Long ni Short
                    if not long_val and not short_val:
                        continue

                    ligne = {
                        "Trade Date":    trade_date,
                        "Trade Number":  trade_number,
                        "Long":          long_val,
                        "Short":         short_val,
                        "Product":       current_contract,
                        "Mon":           mon,
                        "Yr":            yr,
                        "CCY":           "EUR",
                    }
                    toutes_les_lignes.append(ligne)
                    print(f"  ✅ {ligne}")

    print(f"\n📊 Total lignes extraites : {len(toutes_les_lignes)}")
    return toutes_les_lignes