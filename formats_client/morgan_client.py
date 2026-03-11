import pandas as pd
import re

# Dictionnaire de correspondances spéciales PDF → mots-clés à chercher dans Sec Desc
MAPPING_PRODUITS = {
    "ULTRALTBOND":  "ULTRATBOND",
    "ULTRA10NOTE":  "ULTRA10YRNOTE",
    "3YRGOVTBOND":  "3YRBOND",
    "10YRGOVTBOND": "10YRBOND",
    "10YRNOTE":     "10YRNOTE",
    "2YRNOTE":      "2YRNOTE",
    "5YRNOTE":      "5YRNOTE",
}

def charger_client(chemin_excel):
    """
    Détecte automatiquement la ligne de header
    en cherchant la ligne qui contient 'Portfolio' ou 'Buy'
    """
    # Lire sans header pour trouver la bonne ligne
    df_raw = pd.read_excel(chemin_excel, header=None)
    
    header_row = 0
    code_client = ""
    
    for i, row in df_raw.iterrows():
        valeurs = [str(v).strip() for v in row if pd.notna(v)]
        texte_ligne = " ".join(valeurs)
        
        # Chercher le code client dans PortGroup
        if "PortGroup" in texte_ligne or "PortGroup" in texte_ligne:
            m = re.search(r'PortGroup\s*=\s*([^\n]+)', texte_ligne)
            if m:
                print(f"   PortGroup trouvé : {m.group(1)}")
        
        # Chercher la ligne header : contient "Portfolio" et "Current Face"
        if any("Portfolio" in v or "Buy" in v for v in valeurs):
            if any("Face" in v or "Sec" in v for v in valeurs):
                header_row = i
                print(f"✅ Header trouvé à la ligne {i+1} : {valeurs[:5]}")
                break
    
    # Relire avec le bon header
    df = pd.read_excel(chemin_excel, header=header_row)
    df.columns = df.columns.str.strip()
    
    print(f"✅ Colonnes : {list(df.columns)}")
    print(df.head(3).to_string())
    
    return df


def extraire_code_client(df):
    """
    Cherche le code client dans la colonne Portfolio.
    Ex: '3775T' → '3775T'
    """
    col = next((c for c in df.columns if "portfolio" in c.lower() or "portefol" in c.lower()), None)
    if not col:
        print("⚠️  Colonne Portfolio non trouvée !")
        return ""
    
    for val in df[col].dropna():
        val = str(val).strip()
        if val and val != "nan":
            print(f"   Code client : {val}")
            return val
    return ""

def agréger_client(df, code_pdf=None):
    """
    Filtre par Portfolio qui contient le code_pdf
    Ex: code_pdf='3757' → garde uniquement les lignes où Portfolio contient '3757'
    """
    df = df.copy()

    # Détecter colonnes
    col_portfolio = next((c for c in df.columns if "portfolio" in c.lower() or "portefol" in c.lower()), None)
    col_secdesc   = next((c for c in df.columns if c.strip() == "Sec Desc"), None)
    col_face      = next((c for c in df.columns if c.strip() == "Current Face"), None)
    col_currency  = next((c for c in df.columns if c.strip() == "Currency" or c.strip() == "Curren"), None)

    print(f"   Portfolio col : {col_portfolio}")
    print(f"   Sec Desc  col : {col_secdesc}")
    print(f"   Face      col : {col_face}")
    print(f"   Currency  col : {col_currency}")

    # Renommer
    rename_map = {}
    if col_portfolio: rename_map[col_portfolio] = "Portfolio"
    if col_secdesc:   rename_map[col_secdesc]   = "Sec Desc"
    if col_face:      rename_map[col_face]       = "Current Face"
    if col_currency:  rename_map[col_currency]   = "Currency"
    df = df.rename(columns=rename_map)

    # ── Filtrer par code client PDF ──
    if code_pdf and "Portfolio" in df.columns:
        code_norm = str(code_pdf).strip()
        avant = len(df)
        df = df[df["Portfolio"].astype(str).str.contains(code_norm, na=False)]
        print(f"   Filtre Portfolio '{code_norm}' : {avant} → {len(df)} lignes")

    # Garder colonnes utiles
    cols_dispo = [c for c in ["Portfolio", "Sec Desc", "Current Face", "Currency"] if c in df.columns]
    df = df[cols_dispo].copy()

    df = df.dropna(subset=["Sec Desc"])
    df = df[df["Sec Desc"].astype(str).str.strip() != ""]

    df["Current Face"] = pd.to_numeric(df["Current Face"], errors="coerce").fillna(0)
    df["Client_Long"]  = df["Current Face"].apply(lambda x: x  if x > 0 else 0)
    df["Client_Short"] = df["Current Face"].apply(lambda x: -x if x < 0 else 0)

    group_cols = [c for c in ["Sec Desc", "Portfolio"] if c in df.columns]
    resume = df.groupby(group_cols, as_index=False).agg(
        Client_Long =("Client_Long",  "sum"),
        Client_Short=("Client_Short", "sum")
    )

    if "Currency" in df.columns:
        df_currency = df[["Sec Desc", "Currency"]].drop_duplicates("Sec Desc")
        resume = resume.merge(df_currency, on="Sec Desc", how="left")

    resume["Client_Long"]  = resume["Client_Long"].replace(0, "")
    resume["Client_Short"] = resume["Client_Short"].replace(0, "")

    print(f"\n📊 Client agrégé : {len(resume)} produits")
    print(resume.to_string(index=False))
    return resume



def normaliser(texte):
    texte = str(texte).upper().strip()
    texte = re.sub(r'[^A-Z0-9]', '', texte)
    return texte

def construire_cle_pdf(product, mon, yr):
    product_norm   = normaliser(product)
    mon_norm       = normaliser(mon)
    yr_norm        = normaliser(yr)
    product_mapped = MAPPING_PRODUITS.get(product_norm, product_norm)
    return f"{product_mapped}{mon_norm}{yr_norm}"

def calculer_status(pdf_long, pdf_short, client_long, client_short):
    """
    Compare PDF vs Client et retourne un statut.
    """
    # Convertir en nombres pour comparer
    def to_num(val):
        try:
            return float(str(val).replace(",", "")) if val != "" else 0.0
        except:
            return 0.0

    pl = to_num(pdf_long)
    ps = to_num(pdf_short)
    cl = to_num(client_long)
    cs = to_num(client_short)

    if pl == cl and ps == cs:
        return "✅ OK"
    elif pl != cl and ps != cs:
        return "⚠️ ÉCART LONG & SHORT"
    elif pl != cl:
        return "⚠️ ÉCART LONG"
    elif ps != cs:
        return "⚠️ ÉCART SHORT"
    return "✅ OK"


def joindre(df_pdf, df_client):
    resultats = []

    for _, row_pdf in df_pdf.iterrows():
        product = str(row_pdf.get("Product", ""))
        mon     = str(row_pdf.get("Mon", ""))
        yr      = str(row_pdf.get("Yr", ""))
        ccy     = str(row_pdf.get("CCY", ""))
        cle_pdf = construire_cle_pdf(product, mon, yr)

        match_found = False

        for _, row_client in df_client.iterrows():
            sec_desc_norm = normaliser(str(row_client["Sec Desc"]))

            if cle_pdf in sec_desc_norm:
                pdf_long     = row_pdf.get("Total_Long",  "")
                pdf_short    = row_pdf.get("Total_Short", "")
                client_long  = row_client["Client_Long"]
                client_short = row_client["Client_Short"]

                status = calculer_status(pdf_long, pdf_short, client_long, client_short)

                resultats.append({
                    "Portfolio":    row_client.get("Portfolio", ""),
                    "Product":      product,
                    "Mon":          mon,
                    "Yr":           yr,
                    "CCY":          ccy,
                    "Sec Desc":     row_client["Sec Desc"],
                    "PDF_Long":     pdf_long,
                    "PDF_Short":    pdf_short,
                    "Client_Long":  client_long,
                    "Client_Short": client_short,
                    "Status":       status,
                })
                match_found = True
                break

        if not match_found:
            resultats.append({
                "Portfolio":    "",
                "Product":      product,
                "Mon":          mon,
                "Yr":           yr,
                "CCY":          ccy,
                "Sec Desc":     "❌ Non trouvé",
                "PDF_Long":     row_pdf.get("Total_Long",  ""),
                "PDF_Short":    row_pdf.get("Total_Short", ""),
                "Client_Long":  "",
                "Client_Short": "",
                "Status":       "❌ NON TROUVÉ",
            })

    return pd.DataFrame(resultats, columns=[
        "Portfolio", "Product", "Mon", "Yr", "CCY", "Sec Desc",
        "PDF_Long", "PDF_Short", "Client_Long", "Client_Short", "Status"

    ])

