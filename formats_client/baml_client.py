if st.session_state.nom_format == "baml":
    st.markdown("---")
    st.subheader("📋 Comparer avec Doc Client BAML")
    fichier_client = st.file_uploader(
        "Upload Excel client BAML", type=["xlsx","xls"], key="client_baml"
    )
    if fichier_client:
        from formats_client import baml_client
        df_client_raw = baml_client.charger_client(fichier_client)
        df_comp = baml_client.comparer(
            st.session_state.output_df, df_client_raw
        )

        def colorier(row):
            if row["Status"] == "✅ OK":
                return ["background-color: #c6efce"] * len(row)
            elif "ÉCART" in row["Status"]:
                return ["background-color: #ffeb9c"] * len(row)
            else:
                return ["background-color: #ffc7ce"] * len(row)

        st.dataframe(df_comp.style.apply(colorier, axis=1))
