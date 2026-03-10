import pandas as pd
import re

def charger_client(chemin_excel):
    df = pd.read_excel(chemin_excel)
    df.columns = df.columns.str.strip()
    print(f"✅ Colonnes Triton client : {list(df.columns)}")
    return df

def agréger_client(df):
    """
    Volume > 0 → Long
    Volume < 0 → Short
    """
    df = df.copy()
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)

    df["Client_Long"]  = df["Volume"].apply(lambda x: x  if x > 0 else 0)
    df["Client_Short"] = df["Volume"].apply(lambda x: -x if x < 0 else 0)

    resume = df.groupby("InstructionSN", as_index=False).agg(
        TradeDate    =("TradeDate",    "first"),
        Client_Long  =("Client_Long",  "sum"),
        Client_Short =("Client_Short", "sum"),
        Volume       =("Volume",       "sum"),
    )

    resume["Client_Long"]  = resume["Client_Long"].replace(0, "")
    resume["Client_Short"] = resume["Client_Short"].replace(0, "")

    print(f"\n📊 Client Triton agrégé : {len(resume)} lignes")
    print(resume.head(5).to_string(index=False))
    return resume


def joindre(df_pdf, df_client):
    """
    Jointure : Trade Number (PDF) == InstructionSN (Client)
    Comparer Long/Short PDF vs Client
    Output : TradeDate, InstructionSN, Trade Number, Long_triton, Short_triton, Volume, Status
    """
    resultats = []

    for _, row_pdf in df_pdf.iterrows():
        trade_number = str(row_pdf.get("Trade Number", "")).strip()
        long_pdf     = str(row_pdf.get("Long",  "")).strip()
        short_pdf    = str(row_pdf.get("Short", "")).strip()

        # Chercher dans le client
        match = df_client[df_client["InstructionSN"].astype(str) == trade_number]

        if not match.empty:
            row_client   = match.iloc[0]
            client_long  = str(row_client["Client_Long"]).strip()
            client_short = str(row_client["Client_Short"]).strip()
            volume       = row_client["Volume"]
            trade_date   = row_client["TradeDate"]

            status = calculer_status(long_pdf, short_pdf, client_long, client_short)

            resultats.append({
                "Trade Date":     row_pdf.get("Trade Date", ""),
                "Trade Number":   trade_number,
                "InstructionSN":  trade_number,
                "Long_triton":    long_pdf,
                "Short_triton":   short_pdf,
                "Volume":         volume,
                "Status":         status,
            })
        else:
            resultats.append({
                "Trade Date":     row_pdf.get("Trade Date", ""),
                "Trade Number":   trade_number,
                "InstructionSN":  "❌ Non trouvé",
                "Long_triton":    long_pdf,
                "Short_triton":   short_pdf,
                "Volume":         "",
                "Status":         "❌ NON TROUVÉ",
            })

    return pd.DataFrame(resultats, columns=[
        "Trade Date", "Trade Number", "InstructionSN",
        "Long_triton", "Short_triton", "Volume", "Status"
    ])


def calculer_status(pdf_long, pdf_short, client_long, client_short):
    def to_num(val):
        try:
            return float(str(val).replace(",", "")) if val not in ("", "0") else 0.0
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