import re
import pandas as pd
import extract_msg


COLONNES = [
    "Buy/Sell", "Portfolio", "Portfolio Full Name",
    "Custodian", "Current Face", "CUSIP(Aladdin ID)",
    "Sec Desc", "Issue Date", "Maturity"
]


def charger_client(chemin_msg):
    """
    Lire email .msg OFI et extraire le tableau positions.
    Le body est en texte vertical : headers puis valeurs.
    """
    msg  = extract_msg.openMsg(chemin_msg)
    body = msg.body or ""

    lignes = [l.strip() for l in body.split('\n') if l.strip()]

    # Trouver index du premier header "Buy/Sell"
    start = None
    for i, l in enumerate(lignes):
        if l == "Buy/Sell":
            start = i
            break

    if start is None:
        print("⚠️ Header 'Buy/Sell' non trouvé dans l'email")
        return pd.DataFrame(columns=COLONNES)

    # Les N colonnes headers sont en start..start+N
    nb_cols = len(COLONNES)

    # Vérifier que les headers correspondent
    headers_found = lignes[start:start + nb_cols]
    print(f"Headers trouvés: {headers_found}")

    # Les données commencent après les headers
    data_start = start + nb_cols
    data_lines = lignes[data_start:]

    # Lire les lignes par blocs de nb_cols
    rows = []
    i = 0
    while i + nb_cols <= len(data_lines):
        bloc = data_lines[i:i + nb_cols]
        # Arrêter si on sort du tableau
        if any(x in bloc[0] for x in ["Vous pouvez", "Bien à vous", "Salomé", "Middle"]):
            break
        row = dict(zip(COLONNES, bloc))
        rows.append(row)
        i += nb_cols

    df = pd.DataFrame(rows)
    print(f"✅ OFI client : {len(df)} positions")
    print(df.to_string())
    return df


def agréger_client(df):
    """
    Buy/Sell : Sell = Short, Buy = Long
    Current Face = quantité
    """
    df = df.copy()

    def parse_qty(val):
        try:
            return float(str(val).replace(',', '.').replace(' ', ''))
        except:
            return 0.0

    df["_qty"] = df["Current Face"].apply(parse_qty)
    df["Client_Long"]  = df.apply(
        lambda r: r["_qty"] if str(r["Buy/Sell"]).strip().upper() == "BUY"  else 0, axis=1
    )
    df["Client_Short"] = df.apply(
        lambda r: r["_qty"] if str(r["Buy/Sell"]).strip().upper() == "SELL" else 0, axis=1
    )

    resume = df.groupby("Sec Desc", as_index=False).agg(
        Client_Long  = ("Client_Long",  "sum"),
        Client_Short = ("Client_Short", "sum"),
        Portfolio    = ("Portfolio Full Name", "first"),
    )
    return resume


def matcher_produit(product_pdf, df_client):
    """
    PDF    : "CALL PANW 18 JUN 26 185.00"
    Client : "JUN26 PANW C @ 185.000000"
    Tokens communs : PANW, JUN, 26, 185
    """
    norm_pdf = re.sub(r'[^A-Z0-9]', '', product_pdf.upper())

    # Extraire tokens significatifs du PDF
    tokens_pdf = set(re.findall(r'[A-Z0-9]{2,}', product_pdf.upper()))

    best_match = None
    best_score = 0

    for _, row in df_client.iterrows():
        desc = str(row["Sec Desc"]).upper()
        tokens_client = set(re.findall(r'[A-Z0-9]{2,}', desc))
        score = len(tokens_pdf & tokens_client)
        if score > best_score:
            best_score = score
            best_match = row["Sec Desc"]

    return best_match if best_score >= 2 else None


def comparer(df_pdf, df_client_raw):
    df_client = agréger_client(df_client_raw)
    resultats = []

    for _, row in df_pdf.iterrows():
        product_pdf = str(row.get("Product", "")).strip()
        long_pdf    = float(row.get("Long",  0) or 0)
        short_pdf   = float(row.get("Short", 0) or 0)

        match = matcher_produit(product_pdf, df_client)

        if match:
            lc = df_client[df_client["Sec Desc"] == match].iloc[0]
            client_long  = float(lc["Client_Long"])
            client_short = float(lc["Client_Short"])
            ecarts = []
            if long_pdf  != client_long:  ecarts.append("ÉCART LONG")
            if short_pdf != client_short: ecarts.append("ÉCART SHORT")
            status = ("⚠️ " + " & ".join(ecarts)) if ecarts else "✅ OK"
        else:
            match = client_long = client_short = ""
            status = "❌ NON TROUVÉ"

        resultats.append({
            "Product PDF":  product_pdf,
            "Sec Desc":     match,
            "Long PDF":     long_pdf  or "",
            "Short PDF":    short_pdf or "",
            "Client Long":  client_long,
            "Client Short": client_short,
            "Status":       status,
        })

    return pd.DataFrame(resultats)
