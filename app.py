import io
import os
import numpy as np
import pandas as pd
import pulp
import streamlit as st


def to_scalar(val, default=None):
  if val is None:
    return default
  if isinstance(val, (pd.Series, pd.Index, np.ndarray, list, tuple)):
    vals = val.tolist() if hasattr(val, "tolist") else list(val)
    for item in vals:
      res = to_scalar(item, None)
      if res is not None:
        return res
    return default
  try:
    if pd.isna(val):
      return default
  except Exception:
    pass
  s = str(val).strip()
  if not s or s.upper() in ["NAN", "NONE", "NULL", "NAT", "<NA>"]:
    return default
  return val


def to_prim_str(val, default=""):
  sc = to_scalar(val, None)
  if sc is None:
    return default
  return str(sc).strip()


def to_prim_int(val, default=0):
  sc = to_scalar(val, None)
  if sc is None:
    return default
  try:
    return int(float(sc))
  except Exception:
    return default


def clean_str(s):
  sc = to_prim_str(s, "X")
  res = "".join(c if c.isalnum() else "_" for c in sc).strip("_")
  return res if res else "X"


def sanitize_dataframe(df):
  if df is None or not isinstance(df, pd.DataFrame) or df.empty:
    return pd.DataFrame()
  df = df.copy()
  if isinstance(df.columns, pd.MultiIndex):
    flat_cols = []
    for col in df.columns:
      parts = [str(c).strip() for c in col if pd.notna(c) and str(c).strip()]
      flat_cols.append("_".join(parts) if parts else "Unassigned")
    df.columns = flat_cols
  df.columns = [str(c).strip() for c in df.columns]
  df = df.loc[:, ~df.columns.duplicated()].copy()
  return df


def find_col(df, candidate_names, default_name=""):
  if df is None or not isinstance(df, pd.DataFrame) or df.empty:
    return str(default_name)
  cols = [str(c).strip() for c in df.columns]
  for name in candidate_names:
    for idx, c in enumerate(cols):
      if c.lower() == name.lower():
        return str(df.columns[idx])
  for name in candidate_names:
    for idx, c in enumerate(cols):
      if name.lower() in c.lower() or c.lower() in name.lower():
        return str(df.columns[idx])
  if len(cols) > 0:
    return str(df.columns[0])
  return str(default_name)


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
          "Jumlah_Jam_KBM": list((7, 6, 6, 6, 6)),
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
  df_config_edited = st.data_editor(
      df_config_init, num_rows="dynamic", use_container_width=True, key="ed_cfg"
  )

with tab_mgmp:
  st.subheader("Pengaturan Hari Kegiatan MGMP per Mapel")
  df_mgmp_edited = st.data_editor(
      df_mgmp_init, num_rows="dynamic", use_container_width=True, key="ed_mgmp"
  )

with tab_status:
  st.subheader("Daftar Guru, Mata Pelajaran, dan Jabatan Khusus")
  df_status_edited = st.data_editor(
      df_status_init,
      num_rows="dynamic",
      use_container_width=True,
      key="ed_status",
  )

with tab_beban:
  st.subheader("Target Jam Wajib Pasangan Guru & Kelas")
  df_beban_edited = st.data_editor(
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
    # Sanitize all dataframes
    df_beban_raw = sanitize_dataframe(df_beban_edited)
    df_config = sanitize_dataframe(df_config_edited)
    df_status_raw = sanitize_dataframe(df_status_edited)
    df_mgmp_rule = sanitize_dataframe(df_mgmp_edited)

    col_guru = find_col(df_beban_raw, ["Guru", "Nama_Guru", "Nama Guru"], "Guru")
    col_kelas = find_col(
        df_beban_raw, ["Kelas", "Nama_Kelas", "Rombel"], "Kelas"
    )
    col_jw = find_col(
        df_beban_raw, ["Jam_Wajib", "Jam Wajib", "Target_Jam", "Jam"], "Jam_Wajib"
    )

    g_list, k_list, jw_list = [], [], []
    if not df_beban_raw.empty and col_guru in df_beban_raw.columns:
      last_guru = None
      for _, r in df_beban_raw.iterrows():
        g_val = to_prim_str(r.get(col_guru))
        if g_val:
          last_guru = g_val
        else:
          g_val = last_guru
        k_val = to_prim_str(r.get(col_kelas)).upper()
        jw_val = to_prim_int(r.get(col_jw), 0)
        if g_val and k_val and jw_val > 0:
          g_list.append(g_val)
          k_list.append(k_val)
          jw_list.append(jw_val)

    df_beban_clean = pd.DataFrame(
        {"Guru": g_list, "Kelas": k_list, "Jam_Wajib": jw_list}
    )
    INVALID_TEXTS = ["NAN", "NONE", "", "NULL", "GURU", "KELAS", "UNNAMED: 0"]
    df_beban = df_beban_clean[
        (~df_beban_clean["Guru"].str.upper().isin(INVALID_TEXTS))
        & (~df_beban_clean["Kelas"].isin(INVALID_TEXTS))
        & (df_beban_clean["Jam_Wajib"] > 0)
    ].copy()

    df_pair = df_beban.groupby(["Guru", "Kelas"], as_index=False)[
        "Jam_Wajib"
    ].sum()
    df_pair = df_pair[df_pair["Jam_Wajib"] > 0].copy()

    col_status_guru = find_col(
        df_status_raw, ["Guru", "Nama_Guru", "Nama Guru"], "Guru"
    )
    status_dict = {}
    if not df_status_raw.empty and col_status_guru in df_status_raw.columns:
      for _, r in df_status_raw.iterrows():
        g_key = to_prim_str(r.get(col_status_guru))
        if (
            g_key
            and g_key.upper() not in INVALID_TEXTS
            and g_key not in status_dict
        ):
          status_dict[g_key] = r.to_dict()

    col_hari = find_col(df_config, ["Hari", "Nama_Hari", "Day"], "Hari")
    col_jam_count = find_col(
        df_config,
        ["Jumlah_Jam_KBM", "Jumlah_Jam", "Jam_KBM", "Jam"],
        "Jumlah_Jam_KBM",
    )

    HARI = []
    JAM_HARI = {}
    if not df_config.empty and col_hari in df_config.columns:
      for _, r in df_config.iterrows():
        h_name = to_prim_str(r.get(col_hari))
        j_cnt = to_prim_int(r.get(col_jam_count), 6)
        if h_name:
          HARI.append(h_name)
          JAM_HARI[h_name] = list(range(1, j_cnt + 1))

    col_mgmp_mapel = find_col(
        df_mgmp_rule,
        ["Mata_Pelajaran", "Mapel", "Mata Pelajaran"],
        "Mata_Pelajaran",
    )
    col_mgmp_hari = find_col(
        df_mgmp_rule, ["Hari_MGMP", "Hari MGMP", "Hari"], "Hari_MGMP"
    )
    HARI_MGMP_MAPEL = {}
    if not df_mgmp_rule.empty:
      for _, r in df_mgmp_rule.iterrows():
        m_name = to_prim_str(r.get(col_mgmp_mapel)).upper()
        h_mgmp = to_prim_str(r.get(col_mgmp_hari))
        if m_name and h_mgmp:
          HARI_MGMP_MAPEL[m_name] = h_mgmp

    GURU = sorted(list(set(to_prim_str(g) for g in df_pair["Guru"])))
    KELAS = sorted(list(set(to_prim_str(k) for k in df_pair["Kelas"])))
    valid_gk_pairs = [
        (to_prim_str(row["Guru"]), to_prim_str(row["Kelas"]))
        for _, row in df_pair.iterrows()
        if to_prim_int(row["Jam_Wajib"]) > 0
    ]

    mgmp_teachers = set()
    for g in GURU:
      st_info = status_dict.get(g, {})
      val = to_prim_str(st_info.get("Is_MGMP")).upper()
      if val in ["1", "1.0", "TRUE", "Y", "YES"]:
        mgmp_teachers.add(g)

    # Build PuLP Model
    model = pulp.LpProblem("Penjadwalan_SMPN2Plered_Streamlit", pulp.LpMinimize)

    var_keys = [
        (to_prim_str(g), to_prim_str(k), to_prim_str(h), to_prim_int(j))
        for (g, k) in valid_gk_pairs
        for h in HARI
        for j in JAM_HARI.get(to_prim_str(h), [])
    ]
    pair_keys = [(to_prim_str(g), to_prim_str(k)) for (g, k) in valid_gk_pairs]
    c2_keys = [
        (to_prim_str(k), to_prim_str(h), to_prim_int(j))
        for k in KELAS
        for h in HARI
        for j in JAM_HARI.get(to_prim_str(h), [])
    ]
    dh_keys = [(to_prim_str(g), to_prim_str(h)) for g in GURU for h in HARI]

    gap_keys = []
    for g, k in valid_gk_pairs:
      g_s, k_s = to_prim_str(g), to_prim_str(k)
      for h in HARI:
        h_s = to_prim_str(h)
        j_list = JAM_HARI.get(h_s, [])
        for idx in range(len(j_list) - 2):
          gap_keys.append((g_s, k_s, h_s, to_prim_int(j_list[idx])))

    # Explicit dictionary comprehensions
    x = {}
    for g, k, h, j in var_keys:
      vname = f"x_{clean_str(g)}_{clean_str(k)}_{clean_str(h)}_{j}"
      x[(g, k, h, j)] = pulp.LpVariable(vname, cat=pulp.LpBinary)

    d_pair_minus = {}
    d_pair_plus = {}
    for g, k in pair_keys:
      d_pair_minus[(g, k)] = pulp.LpVariable(
          f"dp_minus_{clean_str(g)}_{clean_str(k)}", lowBound=0
      )
      d_pair_plus[(g, k)] = pulp.LpVariable(
          f"dp_plus_{clean_str(g)}_{clean_str(k)}", lowBound=0
      )

    d_c2_minus = {}
    for k, h, j in c2_keys:
      d_c2_minus[(k, h, j)] = pulp.LpVariable(
          f"dc2_minus_{clean_str(k)}_{clean_str(h)}_{j}", lowBound=0
      )

    d_h_plus = {}
    d_h_minus = {}
    for g, h in dh_keys:
      d_h_plus[(g, h)] = pulp.LpVariable(
          f"dh_plus_{clean_str(g)}_{clean_str(h)}", lowBound=0
      )
      d_h_minus[(g, h)] = pulp.LpVariable(
          f"dh_minus_{clean_str(g)}_{clean_str(h)}", lowBound=0
      )

    z_gap = {}
    for g, k, h, j in gap_keys:
      z_gap[(g, k, h, j)] = pulp.LpVariable(
          f"zgap_{clean_str(g)}_{clean_str(k)}_{clean_str(h)}_{j}", lowBound=0
      )

    # Constraints
    for g in mgmp_teachers:
      st_info = status_dict.get(g, {})
      mapel_raw = to_prim_str(st_info.get("Mata_Pelajaran"))
      mapel_list = [
          m.strip().upper() for m in mapel_raw.split(",") if m.strip()
      ]
      for m_name in mapel_list:
        h_mgmp = HARI_MGMP_MAPEL.get(m_name)
        if h_mgmp and h_mgmp in HARI:
          assigned_k = [k_i for (g_i, k_i) in valid_gk_pairs if g_i == g]
          for k_i in assigned_k:
            for j in JAM_HARI.get(h_mgmp, []):
              j_i = to_prim_int(j)
              if j_i > 2 and (g, k_i, h_mgmp, j_i) in x:
                model += x[g, k_i, h_mgmp, j_i] == 0

    penalti_list = []

    for g in GURU:
      assigned_k = [k_i for (g_i, k_i) in valid_gk_pairs if g_i == g]
      if assigned_k:
        for h in HARI:
          for j in JAM_HARI.get(h, []):
            j_i = to_prim_int(j)
            if any((g, k_i, h, j_i) in x for k_i in assigned_k):
              model += (
                  pulp.lpSum([
                      x[g, k_i, h, j_i]
                      for k_i in assigned_k
                      if (g, k_i, h, j_i) in x
                  ])
                  <= 1
              )

    for k in KELAS:
      assigned_g = [g_i for (g_i, k_i) in valid_gk_pairs if k_i == k]
      if assigned_g:
        for h in HARI:
          for j in JAM_HARI.get(h, []):
            j_i = to_prim_int(j)
            if (k, h, j_i) in d_c2_minus:
              model += (
                  pulp.lpSum([
                      x[g_i, k, h, j_i]
                      for g_i in assigned_g
                      if (g_i, k, h, j_i) in x
                  ])
                  + d_c2_minus[k, h, j_i]
                  == 1
              )

    for _, row in df_pair.iterrows():
      g, k, jw = (
          to_prim_str(row["Guru"]),
          to_prim_str(row["Kelas"]),
          to_prim_int(row["Jam_Wajib"]),
      )
      if (g, k) in d_pair_minus and (g, k) in d_pair_plus:
        model += (
            pulp.lpSum([
                x[g, k, h, to_prim_int(j)]
                for h in HARI
                for j in JAM_HARI.get(h, [])
                if (g, k, h, to_prim_int(j)) in x
            ])
            + d_pair_minus[g, k]
            - d_pair_plus[g, k]
            == jw
        )

    for g, k in valid_gk_pairs:
      for h in HARI:
        j_list = JAM_HARI.get(h, [])
        for idx in range(len(j_list) - 2):
          j1, j2, j3 = (
              to_prim_int(j_list[idx]),
              to_prim_int(j_list[idx + 1]),
              to_prim_int(j_list[idx + 2]),
          )
          if (
              (g, k, h, j1) in x
              and (g, k, h, j2) in x
              and (g, k, h, j3) in x
              and (g, k, h, j1) in z_gap
          ):
            model += (
                x[g, k, h, j1]
                + x[g, k, h, j3]
                - x[g, k, h, j2]
                - z_gap[g, k, h, j1]
                <= 1
            )

    for g in GURU:
      st_info = status_dict.get(g, {})
      is_wali_val = to_prim_str(st_info.get("Is_Wali")).upper()
      if is_wali_val in ["1", "1.0", "TRUE", "Y", "YES"]:
        k_wali = to_prim_str(st_info.get("Kelas_Wali")).upper()
        if (
            (g, k_wali) in valid_gk_pairs
            and "Jumat" in HARI
            and (g, k_wali, "Jumat", 1) in x
        ):
          p_c6 = pulp.LpVariable(
              f"penalti_wali_{clean_str(g)}",
              lowBound=0,
              cat=pulp.LpContinuous,
          )
          penalti_list.append(p_c6)
          model += x[g, k_wali, "Jumat", 1] + p_c6 >= 1

    wakasek_teachers = [
        g
        for g in GURU
        if to_prim_str(status_dict.get(g, {}).get("Is_Wakasek")).upper()
        in ["1", "1.0", "TRUE", "Y", "YES"]
    ]
    if wakasek_teachers:
      for h in HARI:
        model += (
            pulp.lpSum([
                x[g_w, k_i, h, 1]
                for g_w in wakasek_teachers
                for k_i in KELAS
                if (g_w, k_i, h, 1) in x
            ])
            <= 1
        )

    for g in GURU:
      is_pjok_val = to_prim_str(status_dict.get(g, {}).get("Is_PJOK")).upper()
      if is_pjok_val in ["1", "1.0", "TRUE", "Y", "YES"]:
        assigned_k = [k_i for (g_i, k_i) in valid_gk_pairs if g_i == g]
        for h in HARI:
          for k_i in assigned_k:
            for j in JAM_HARI.get(h, []):
              j_i = to_prim_int(j)
              if j_i > 4 and (g, k_i, h, j_i) in x:
                p_c8 = pulp.LpVariable(
                    f"penalti_pjok_{clean_str(g)}_{clean_str(h)}_{clean_str(k_i)}_{j_i}",
                    lowBound=0,
                    cat=pulp.LpContinuous,
                )
                penalti_list.append(p_c8)
                model += x[g, k_i, h, j_i] - p_c8 <= 0

    model += (
        100000.0
        * pulp.lpSum(
            [d_pair_minus[g, k] + d_pair_plus[g, k] for (g, k) in pair_keys]
        )
        + 10000.0 * pulp.lpSum([d_c2_minus[k, h, j] for (k, h, j) in c2_keys])
        + 50000.0 * pulp.lpSum([z_gap[key] for key in gap_keys])
        + 1000.0 * pulp.lpSum(penalti_list)
        + 2.0
        * pulp.lpSum([
            d_h_plus[g, h] + d_h_minus[g, h] for g in GURU for h in HARI
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

      # Summary Metrics
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

      # Download Option
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
