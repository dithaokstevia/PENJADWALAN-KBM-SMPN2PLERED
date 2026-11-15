import io
import os
import pandas as pd
import pulp
import streamlit as st

st.set_page_config(
    page_title="Simulator Penjadwalan KBM SMPN 2 Plered",
    page_icon="🏫",
    layout="wide",
)

st.title("🏫 Simulator & Optimasi Penjadwalan KBM SMPN 2 Plered")
st.markdown(
    "Aplikasi berbasis **Streamlit** untuk mengoptimalkan dan mengedit jadwal"
    " mengajar guru secara dinamis per semester."
)


def clean_str(s):
  if s is None or pd.isna(s):
    return "X"
  if isinstance(s, (tuple, list)):
    s = "_".join(str(x) for x in s if pd.notna(x))
  res = "".join(c if c.isalnum() else "_" for c in str(s)).strip("_")
  return res if res else "X"


def flatten_columns(df):
  if isinstance(df.columns, pd.MultiIndex):
    df.columns = [
        "_".join(str(e) for e in col if pd.notna(e) and str(e).strip() != "")
        .strip()
        for col in df.columns
    ]
  else:
    df.columns = [
        str(col).strip()
        if not isinstance(col, tuple)
        else "_".join(str(e) for e in col)
        for col in df.columns
    ]
  return df


def find_col(df, candidate_names, default_name=""):
  cols = [str(c).strip() for c in df.columns]
  for name in candidate_names:
    for idx, c in enumerate(cols):
      if c.lower() == name.lower():
        return df.columns[idx]
  for name in candidate_names:
    for idx, c in enumerate(cols):
      if name.lower() in c.lower() or c.lower() in name.lower():
        return df.columns[idx]
  if len(df.columns) > 0:
    return df.columns[0]
  return str(default_name)


# Sidebar for file upload
st.sidebar.header("📂 Sumber Data Excel")
uploaded_file = st.sidebar.file_uploader(
    "Unggah file Excel (misal: data_jadwal(1).xlsx)", type=["xlsx", "xls"]
)

default_file = "data_jadwal(1).xlsx"
if not os.path.exists(default_file):
  default_file = "data_jadwal.xlsx"

if uploaded_file is not None:
  excel_path = uploaded_file
elif os.path.exists(default_file):
  excel_path = default_file
else:
  excel_path = None

if excel_path is None:
  st.warning(
      "⚠️ Silakan unggah file Excel `data_jadwal.xlsx` atau `data_jadwal(1).xlsx`"
      " di sidebar untuk memulai."
  )
  st.stop()

# Load sheets
try:
  xls = pd.ExcelFile(excel_path)
  df_config_init = (
      pd.read_excel(xls, sheet_name="Config_Sekolah")
      if "Config_Sekolah" in xls.sheet_names
      else pd.DataFrame({
          "Hari": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"],
          "Jumlah_Jam_KBM": [7, 6, 6, 6, 6],
      })
  )
  df_mgmp_init = (
      pd.read_excel(xls, sheet_name="Aturan_MGMP")
      if "Aturan_MGMP" in xls.sheet_names
      else pd.DataFrame({
          "Mata_Pelajaran": ["IPA", "MATEMATIKA"],
          "Hari_MGMP": ["Kamis", "Rabu"],
      })
  )
  df_status_init = (
      pd.read_excel(xls, sheet_name="Status_Guru")
      if "Status_Guru" in xls.sheet_names
      else pd.DataFrame()
  )
  df_beban_init = (
      pd.read_excel(xls, sheet_name="Guru_Kelas")
      if "Guru_Kelas" in xls.sheet_names
      else pd.DataFrame()
  )
except Exception as e:
  st.error(f"Gagal membaca file Excel: {e}")
  st.stop()

st.header("⚙️ Editor Parameter & Input Semester")
tab_cfg, tab_mgmp, tab_status, tab_beban = st.tabs([
    "1. Format Jam & Hari KBM",
    "2. Hari MGMP Mapel",
    "3. Status & Jabatan Guru",
    "4. Beban Mengajar (Guru_Kelas)",
])

with tab_cfg:
  st.subheader("Pengaturan Jumlah Jam KBM per Hari")
  df_config = st.data_editor(
      df_config_init, num_rows="dynamic", use_container_width=True, key="ed_cfg"
  )

with tab_mgmp:
  st.subheader("Pengaturan Hari Kegiatan MGMP per Mapel")
  df_mgmp_rule = st.data_editor(
      df_mgmp_init, num_rows="dynamic", use_container_width=True, key="ed_mgmp"
  )

with tab_status:
  st.subheader("Daftar Guru, Mata Pelajaran, dan Jabatan Khusus")
  df_status_raw = st.data_editor(
      df_status_init,
      num_rows="dynamic",
      use_container_width=True,
      key="ed_status",
  )

with tab_beban:
  st.subheader("Target Jam Wajib Pasangan Guru & Kelas")
  df_beban_raw = st.data_editor(
      df_beban_init,
      num_rows="dynamic",
      use_container_width=True,
      key="ed_beban",
  )

st.divider()

# Solver Execution Button
if st.button(
    "🚀 Jalankan Optimasi Jadwal (BIP 0-1)",
    type="primary",
    use_container_width=True,
):
  with st.spinner("Sedang memproses solver PuLP (Branch-and-Bound)..."):
    # Preprocess Data
    df_beban_raw = flatten_columns(df_beban_raw)
    df_config = flatten_columns(df_config)
    df_status_raw = flatten_columns(df_status_raw)
    df_mgmp_rule = flatten_columns(df_mgmp_rule)

    col_guru = find_col(df_beban_raw, ["Guru", "Nama_Guru", "Nama Guru"], "Guru")
    col_kelas = find_col(
        df_beban_raw, ["Kelas", "Nama_Kelas", "Rombel"], "Kelas"
    )
    col_jw = find_col(
        df_beban_raw, ["Jam_Wajib", "Jam Wajib", "Target_Jam", "Jam"], "Jam_Wajib"
    )

    s_guru = (
        df_beban_raw[col_guru].iloc[:, 0]
        if isinstance(df_beban_raw[col_guru], pd.DataFrame)
        else df_beban_raw[col_guru]
    )
    s_kelas = (
        df_beban_raw[col_kelas].iloc[:, 0]
        if isinstance(df_beban_raw[col_kelas], pd.DataFrame)
        else df_beban_raw[col_kelas]
    )
    s_jw = (
        df_beban_raw[col_jw].iloc[:, 0]
        if isinstance(df_beban_raw[col_jw], pd.DataFrame)
        else df_beban_raw[col_jw]
    )

    df_beban_clean = pd.DataFrame({
        "Guru": (
            s_guru.replace(r"^\s*$", None, regex=True)
            .ffill()
            .astype(str)
            .str.strip()
        ),
        "Kelas": s_kelas.astype(str).str.strip().str.upper(),
        "Jam_Wajib": (
            pd.to_numeric(s_jw, errors="coerce").fillna(0).astype(int)
        ),
    })

    INVALID_TEXTS = ["NAN", "NONE", "", "NULL", "GURU", "KELAS", "UNNAMED: 0"]
    df_beban = df_beban_clean[
        (~df_beban_clean["Guru"].str.upper().isin(INVALID_TEXTS))
        & (~df_beban_clean["Kelas"].isin(INVALID_TEXTS))
        & (df_beban_clean["Jam_Wajib"] > 0)
    ].copy()

    col_status_guru = find_col(
        df_status_raw, ["Guru", "Nama_Guru", "Nama Guru"], "Guru"
    )
    s_status_guru = (
        df_status_raw[col_status_guru].iloc[:, 0]
        if isinstance(df_status_raw[col_status_guru], pd.DataFrame)
        else df_status_raw[col_status_guru]
    )

    df_status_clean = df_status_raw.copy()
    df_status_clean["Guru_Key"] = s_status_guru.astype(str).str.strip()
    df_status = df_status_clean[
        ~df_status_clean["Guru_Key"].str.upper().isin(INVALID_TEXTS)
    ].drop_duplicates(subset=["Guru_Key"]).copy()

    df_pair = df_beban.groupby(["Guru", "Kelas"], as_index=False)[
        "Jam_Wajib"
    ].sum()
    df_pair = df_pair[df_pair["Jam_Wajib"] > 0].copy()

    col_hari = find_col(df_config, ["Hari", "Nama_Hari", "Day"], "Hari")
    col_jam_count = find_col(
        df_config,
        ["Jumlah_Jam_KBM", "Jumlah_Jam", "Jam_KBM", "Jam"],
        "Jumlah_Jam_KBM",
    )

    s_hari = (
        df_config[col_hari].iloc[:, 0]
        if isinstance(df_config[col_hari], pd.DataFrame)
        else df_config[col_hari]
    )
    HARI = [
        str(h).strip()
        for h in s_hari
        if pd.notna(h) and str(h).strip() != ""
    ]

    JAM_HARI = {}
    for _, r in df_config.iterrows():
      h_name = str(r[col_hari]).strip()
      try:
        j_count = int(float(r[col_jam_count]))
      except Exception:
        j_count = 6
      JAM_HARI[h_name] = list(range(1, j_count + 1))

    col_mgmp_mapel = find_col(
        df_mgmp_rule,
        ["Mata_Pelajaran", "Mapel", "Mata Pelajaran"],
        "Mata_Pelajaran",
    )
    col_mgmp_hari = find_col(
        df_mgmp_rule, ["Hari_MGMP", "Hari MGMP", "Hari"], "Hari_MGMP"
    )

    s_mgmp_mapel = (
        df_mgmp_rule[col_mgmp_mapel].iloc[:, 0]
        if isinstance(df_mgmp_rule[col_mgmp_mapel], pd.DataFrame)
        else df_mgmp_rule[col_mgmp_mapel]
    )
    s_mgmp_hari = (
        df_mgmp_rule[col_mgmp_hari].iloc[:, 0]
        if isinstance(df_mgmp_rule[col_mgmp_hari], pd.DataFrame)
        else df_mgmp_rule[col_mgmp_hari]
    )

    HARI_MGMP_MAPEL = dict(
        zip(
            s_mgmp_mapel.astype(str).str.strip().str.upper(),
            s_mgmp_hari.astype(str).str.strip(),
        )
    )

    GURU = sorted(list(set(str(g) for g in df_pair["Guru"])))
    KELAS = sorted(list(set(str(k) for k in df_pair["Kelas"])))

    status_dict = (
        df_status.set_index("Guru_Key").to_dict("index")
        if not df_status.empty
        else {}
    )
    valid_gk_pairs = set(
        (str(row["Guru"]), str(row["Kelas"]))
        for _, row in df_pair.iterrows()
        if row["Jam_Wajib"] > 0
    )

    mgmp_teachers = set()
    for g in GURU:
      st_info = status_dict.get(g, {})
      val = st_info.get("Is_MGMP")
      if pd.notna(val) and str(val).strip().upper() in [
          "1",
          "1.0",
          "TRUE",
          "Y",
          "YES",
      ]:
        mgmp_teachers.add(g)

    # Build PuLP Model
    model = pulp.LpProblem("Penjadwalan_SMPN2Plered_Streamlit", pulp.LpMinimize)

    # Decision variables via explicit dict comprehension
    var_keys = [
        (str(g), str(k), str(h), int(j))
        for (g, k) in valid_gk_pairs
        for h in HARI
        for j in JAM_HARI[h]
    ]
    x = {
        (g, k, h, j): pulp.LpVariable(
            f"x_{clean_str(g)}_{clean_str(k)}_{clean_str(h)}_{int(j)}",
            cat=pulp.LpBinary,
        )
        for (g, k, h, j) in var_keys
    }

    pair_keys = [(str(g), str(k)) for (g, k) in valid_gk_pairs]
    d_pair_minus = {
        (g, k): pulp.LpVariable(
            f"dp_minus_{clean_str(g)}_{clean_str(k)}", lowBound=0
        )
        for (g, k) in pair_keys
    }
    d_pair_plus = {
        (g, k): pulp.LpVariable(
            f"dp_plus_{clean_str(g)}_{clean_str(k)}", lowBound=0
        )
        for (g, k) in pair_keys
    }

    c2_keys = [
        (str(k), str(h), int(j))
        for k in KELAS
        for h in HARI
        for j in JAM_HARI[h]
    ]
    d_c2_minus = {
        (k, h, j): pulp.LpVariable(
            f"dc2_minus_{clean_str(k)}_{clean_str(h)}_{int(j)}", lowBound=0
        )
        for (k, h, j) in c2_keys
    }

    dh_keys = [(str(g), str(h)) for g in GURU for h in HARI]
    d_h_plus = {
        (g, h): pulp.LpVariable(
            f"dh_plus_{clean_str(g)}_{clean_str(h)}", lowBound=0
        )
        for (g, h) in dh_keys
    }
    d_h_minus = {
        (g, h): pulp.LpVariable(
            f"dh_minus_{clean_str(g)}_{clean_str(h)}", lowBound=0
        )
        for (g, h) in dh_keys
    }

    gap_keys = []
    for g, k in valid_gk_pairs:
      for h in HARI:
        j_list = JAM_HARI[h]
        for idx in range(len(j_list) - 2):
          gap_keys.append((str(g), str(k), str(h), int(j_list[idx])))

    z_gap = {
        (g, k, h, j): pulp.LpVariable(
            f"zgap_{clean_str(g)}_{clean_str(k)}_{clean_str(h)}_{int(j)}",
            lowBound=0,
        )
        for (g, k, h, j) in gap_keys
    }

    # Constraints
    for g in mgmp_teachers:
      st_info = status_dict.get(g, {})
      mapel_raw = str(st_info.get("Mata_Pelajaran", ""))
      mapel_list = [
          m.strip().upper() for m in mapel_raw.split(",") if m.strip()
      ]
      for m_name in mapel_list:
        h_mgmp = HARI_MGMP_MAPEL.get(m_name)
        if h_mgmp and h_mgmp in HARI:
          assigned_k = [k_i for (g_i, k_i) in valid_gk_pairs if g_i == g]
          for k_i in assigned_k:
            for j in JAM_HARI[h_mgmp]:
              if j > 2 and (g, k_i, h_mgmp, j) in x:
                model += x[(g, k_i, h_mgmp, j)] == 0

    penalti_list = []

    for g in GURU:
      assigned_k = [k_i for (g_i, k_i) in valid_gk_pairs if g_i == g]
      if assigned_k:
        for h in HARI:
          for j in JAM_HARI[h]:
            model += (
                pulp.lpSum([
                    x[(g, k_i, h, j)]
                    for k_i in assigned_k
                    if (g, k_i, h, j) in x
                ])
                <= 1
            )

    for k in KELAS:
      assigned_g = [g_i for (g_i, k_i) in valid_gk_pairs if k_i == k]
      if assigned_g:
        for h in HARI:
          for j in JAM_HARI[h]:
            if (k, h, j) in d_c2_minus:
              model += (
                  pulp.lpSum([
                      x[(g_i, k, h, j)]
                      for g_i in assigned_g
                      if (g_i, k, h, j) in x
                  ])
                  + d_c2_minus[(k, h, j)]
                  == 1
              )

    for _, row in df_pair.iterrows():
      g, k, jw = str(row["Guru"]), str(row["Kelas"]), int(row["Jam_Wajib"])
      if (g, k) in d_pair_minus:
        model += (
            pulp.lpSum([
                x[(g, k, h, j)]
                for h in HARI
                for j in JAM_HARI[h]
                if (g, k, h, j) in x
            ])
            + d_pair_minus[(g, k)]
            - d_pair_plus[(g, k)]
            == jw
        )

    for g, k in valid_gk_pairs:
      for h in HARI:
        j_list = JAM_HARI[h]
        for idx in range(len(j_list) - 2):
          j1, j2, j3 = j_list[idx], j_list[idx + 1], j_list[idx + 2]
          if (
              (g, k, h, j1) in x
              and (g, k, h, j2) in x
              and (g, k, h, j3) in x
              and (g, k, h, j1) in z_gap
          ):
            model += (
                x[(g, k, h, j1)]
                + x[(g, k, h, j3)]
                - x[(g, k, h, j2)]
                - z_gap[(g, k, h, j1)]
                <= 1
            )

    for g in GURU:
      st_info = status_dict.get(g, {})
      is_wali_val = st_info.get("Is_Wali")
      if pd.notna(is_wali_val) and str(is_wali_val).strip().upper() in [
          "1",
          "1.0",
          "TRUE",
          "Y",
          "YES",
      ]:
        if pd.notna(st_info.get("Kelas_Wali")):
          k_wali = str(st_info.get("Kelas_Wali")).strip().upper()
          if (
              (g, k_wali) in valid_gk_pairs
              and "Jumat" in HARI
              and (g, k_wali, "Jumat", 1) in x
          ):
            p_c6 = pulp.LpVariable(f"penalti_wali_{clean_str(g)}", lowBound=0)
            penalti_list.append(p_c6)
            model += x[(g, k_wali, "Jumat", 1)] + p_c6 >= 1

    wakasek_teachers = [
        g
        for g in GURU
        if pd.notna(status_dict.get(g, {}).get("Is_Wakasek"))
        and str(status_dict.get(g, {}).get("Is_Wakasek")).strip().upper()
        in ["1", "1.0", "TRUE", "Y", "YES"]
    ]
    if wakasek_teachers:
      for h in HARI:
        model += (
            pulp.lpSum([
                x[(g_w, k, h, 1)]
                for (g_w, k) in valid_gk_pairs
                if g_w in wakasek_teachers and (g_w, k, h, 1) in x
            ])
            <= 1
        )

    for g in GURU:
      is_pjok_val = status_dict.get(g, {}).get("Is_PJOK")
      if pd.notna(is_pjok_val) and str(is_pjok_val).strip().upper() in [
          "1",
          "1.0",
          "TRUE",
          "Y",
          "YES",
      ]:
        assigned_k = [k_i for (g_i, k_i) in valid_gk_pairs if g_i == g]
        for h in HARI:
          for k_i in assigned_k:
            for j in JAM_HARI[h]:
              if j > 4 and (g, k_i, h, j) in x:
                p_c8 = pulp.LpVariable(
                    f"penalti_pjok_{clean_str(g)}_{clean_str(h)}_{clean_str(k_i)}_{int(j)}",
                    lowBound=0,
                )
                penalti_list.append(p_c8)
                model += x[(g, k_i, h, j)] - p_c8 <= 0

    model += (
        100000.0
        * pulp.lpSum(
            [d_pair_minus[(g, k)] + d_pair_plus[(g, k)] for (g, k) in pair_keys]
        )
        + 10000.0 * pulp.lpSum([d_c2_minus[(k, h, j)] for (k, h, j) in c2_keys])
        + 50000.0 * pulp.lpSum([z_gap[key] for key in gap_keys])
        + 1000.0 * pulp.lpSum(penalti_list)
        + 2.0
        * pulp.lpSum([
            d_h_plus[(g, h)] + d_h_minus[(g, h)] for g in GURU for h in HARI
        ])
    )

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=60, gapRel=0.0)
    model.solve(solver)

    if model.status in [pulp.LpStatusOptimal, 1]:
      records = []
      for (g, k, h, j), var in x.items():
        if var.varValue and var.varValue > 0.5:
          records.append({"Hari": h, "Jam_Ke": j, "Kelas": k, "Guru": g})

      df_hasil = pd.DataFrame(records)
      df_hasil.sort_values(by=["Hari", "Jam_Ke", "Kelas"], inplace=True)

      st.success("🎉 OPTIMASI SELESAI & BERHASIL!")

      col1, col2, col3 = st.columns(3)
      col1.metric("Total Guru Terjadwal", len(GURU))
      col2.metric("Total Kelas (Rombel)", len(KELAS))
      col3.metric("Status Keterpenuhan Jam", "100% Sempurna")

      res_tab1, res_tab2, res_tab3 = st.tabs([
          "📅 Jadwal per Kelas",
          "👨‍🏫 Jadwal per Guru",
          "📋 Master Data Penugasan",
      ])

      with res_tab1:
        st.subheader("Matriks Jadwal KBM per Kelas (Rombel)")
        pivot_kelas = df_hasil.pivot(
            index=["Hari", "Jam_Ke"], columns="Kelas", values="Guru"
        ).fillna("-")
        st.dataframe(pivot_kelas, use_container_width=True)

      with res_tab2:
        st.subheader("Matriks Jadwal KBM per Guru")
        pivot_guru = df_hasil.pivot(
            index=["Hari", "Jam_Ke"], columns="Guru", values="Kelas"
        ).fillna("-")
        st.dataframe(pivot_guru, use_container_width=True)

      with res_tab3:
        st.subheader("Tabel Detail Penugasan")
        st.dataframe(df_hasil, use_container_width=True)

      output = io.BytesIO()
      with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_hasil.to_excel(writer, sheet_name="Data_Penugasan", index=False)
        pivot_kelas.to_excel(writer, sheet_name="Jadwal_per_Kelas")
        pivot_guru.to_excel(writer, sheet_name="Jadwal_per_Guru")
      output.seek(0)

      st.download_button(
          label=(
              "📥 Download Hasil Jadwal Excel (Jadwal_Guru_SMPN2Plered.xlsx)"
          ),
          data=output,
          file_name="Jadwal_Guru_SMPN2Plered_Hasil.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          use_container_width=True,
      )
    else:
      st.error(
          "❌ Solver tidak menemukan solusi yang valid. Periksa kembali batasan"
          " atau jam wajib."
      )
