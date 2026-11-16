import io
import os
import re
import numpy as np
import pandas as pd
import pulp
import streamlit as st


def create_var(name, low_bound=None, up_bound=None, cat=pulp.LpContinuous):
  """Pabrik variabel PuLP universal (kompatibel dengan PuLP 2.x & 3.x)."""
  try:
    kw = {}
    if cat is not None:
      kw["cat"] = cat
    if low_bound is not None:
      kw["low_bound"] = low_bound
    if up_bound is not None:
      kw["up_bound"] = up_bound
    return pulp.LpVariable(name, **kw)
  except TypeError:
    pass

  try:
    kw = {}
    if cat is not None:
      kw["cat"] = cat
    if low_bound is not None:
      kw["lowBound"] = low_bound
    if up_bound is not None:
      kw["upBound"] = up_bound
    return pulp.LpVariable(name, **kw)
  except TypeError:
    pass

  return pulp.LpVariable(name)


def force_str(val, default=""):
  if val is None:
    return default
  if isinstance(
      val, (pd.Series, pd.DataFrame, pd.Index, np.ndarray, list, tuple)
  ):
    if hasattr(val, "values"):
      vals = val.values.flatten()
    else:
      vals = list(val)
    for item in vals:
      s = force_str(item, default="")
      if s:
        return str(s)
    return default
  try:
    if pd.isna(val):
      return default
  except Exception:
    pass
  s = str(val).strip()
  if not s or s.upper() in ["NAN", "NONE", "NULL", "NAT", "<NA>"]:
    return default
  return str(s)


def force_int(val, default=0):
  s = force_str(val, None)
  if s is None:
    return default
  try:
    return int(float(s))
  except Exception:
    return default


def safe_name(s):
  sc = force_str(s, "X")
  res = re.sub(r"\W+", "_", sc).strip("_")
  return res if res else "X"


def sanitize_df(df):
  if df is None or not isinstance(df, pd.DataFrame) or df.empty:
    return pd.DataFrame()
  df = df.copy()
  if isinstance(df.columns, pd.MultiIndex):
    flat = []
    for col in df.columns:
      parts = [
          str(c).strip()
          for c in col
          if pd.notna(c)
          and str(c).strip()
          and not str(c).startswith("Unnamed")
      ]
      flat.append("_".join(parts) if parts else "Col")
    df.columns = flat
  df.columns = [str(c).strip() for c in df.columns]
  df = df.loc[:, ~df.columns.duplicated()].copy()
  return df


def find_col(df, candidate_names, default=""):
  if df is None or df.empty:
    return str(default)
  for name in candidate_names:
    for c in df.columns:
      if str(c).strip().lower() == name.lower():
        return str(c)
  for name in candidate_names:
    for c in df.columns:
      if name.lower() in str(c).strip().lower():
        return str(c)
  return str(default)


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

# Default Initial DataFrames
df_config_init = pd.DataFrame({
    "Hari": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"],
    "Jumlah_Jam_KBM": [7, 6, 6, 6, 6],
})
df_mgmp_init = pd.DataFrame({
    "Mata_Pelajaran": ["IPA", "MATEMATIKA"],
    "Hari_MGMP": ["Kamis", "Rabu"],
})
df_status_init = pd.DataFrame({
    "Guru": ["Guru A", "Guru B"],
    "Mata_Pelajaran": ["IPA", "MATEMATIKA"],
    "Is_Wali": ["0", "0"],
    "Kelas_Wali": ["", ""],
    "Is_Wakasek": ["0", "0"],
    "Is_PJOK": ["0", "0"],
    "Is_MGMP": ["0", "0"],
})
df_beban_init = pd.DataFrame(
    {"Guru": ["Guru A", "Guru B"], "Kelas": ["7A", "7B"], "Jam_Wajib": [2, 2]}
)

excel_path = None
if uploaded_file is not None:
  excel_path = uploaded_file
else:
  for possible_name in [
      "data_jadwal(1).xlsx",
      "data_jadwal.xlsx",
      "data_jadwal(2).xlsx",
  ]:
    if os.path.exists(possible_name):
      excel_path = possible_name
      break

if excel_path is not None:
  try:
    xls = pd.ExcelFile(excel_path)
    sheet_lower = {str(s).lower().strip(): str(s) for s in xls.sheet_names}

    if "config_sekolah" in sheet_lower:
      df_config_init = pd.read_excel(
          xls, sheet_name=sheet_lower["config_sekolah"]
      )
    if "aturan_mgmp" in sheet_lower:
      df_mgmp_init = pd.read_excel(xls, sheet_name=sheet_lower["aturan_mgmp"])
    if "status_guru" in sheet_lower:
      df_status_init = pd.read_excel(
          xls, sheet_name=sheet_lower["status_guru"]
      )
    if "guru_kelas" in sheet_lower:
      df_beban_init = pd.read_excel(xls, sheet_name=sheet_lower["guru_kelas"])
  except Exception as e:
    st.error(f"Gagal membaca file Excel: {e}")

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
    df_beban_raw = sanitize_df(df_beban_edited)
    df_config_raw = sanitize_df(df_config_edited)
    df_status_raw = sanitize_df(df_status_edited)
    df_mgmp_raw = sanitize_df(df_mgmp_edited)

    # 1. Config KBM
    col_hari = find_col(df_config_raw, ["Hari", "Nama_Hari", "Day"], "Hari")
    col_jam_cnt = find_col(
        df_config_raw,
        ["Jumlah_Jam_KBM", "Jumlah_Jam", "Jam_KBM", "Jam"],
        "Jumlah_Jam_KBM",
    )
    HARI = []
    JAM_HARI = {}
    if not df_config_raw.empty and col_hari in df_config_raw.columns:
      for _, r in df_config_raw.iterrows():
        h_val = force_str(r.get(col_hari))
        j_cnt = force_int(r.get(col_jam_cnt), 6)
        if h_val:
          HARI.append(h_val)
          JAM_HARI[h_val] = list(range(1, j_cnt + 1))

    if not HARI:
      HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"]
      JAM_HARI = {h: list(range(1, 7)) for h in HARI}

    # 2. MGMP Rule
    col_mgmp_mapel = find_col(
        df_mgmp_raw,
        ["Mata_Pelajaran", "Mapel", "Mata Pelajaran"],
        "Mata_Pelajaran",
    )
    col_mgmp_hari = find_col(
        df_mgmp_raw, ["Hari_MGMP", "Hari MGMP", "Hari"], "Hari_MGMP"
    )
    HARI_MGMP_MAPEL = {}
    if not df_mgmp_raw.empty:
      for _, r in df_mgmp_raw.iterrows():
        m_name = force_str(r.get(col_mgmp_mapel)).upper()
        h_mgmp = force_str(r.get(col_mgmp_hari))
        if m_name and h_mgmp:
          HARI_MGMP_MAPEL[m_name] = h_mgmp

    # 3. Status Guru
    col_status_guru = find_col(
        df_status_raw, ["Guru", "Nama_Guru", "Nama Guru"], "Guru"
    )
    status_dict = {}
    if not df_status_raw.empty and col_status_guru in df_status_raw.columns:
      for _, r in df_status_raw.iterrows():
        g_key = force_str(r.get(col_status_guru))
        if (
            g_key
            and g_key.upper() not in ["NAN", "NONE", "", "NULL"]
            and g_key not in status_dict
        ):
          status_dict[g_key] = {
              force_str(k): force_str(v) for k, v in r.to_dict().items()
          }

    # 4. Beban Mengajar (Guru_Kelas)
    col_guru = find_col(df_beban_raw, ["Guru", "Nama_Guru", "Nama Guru"], "Guru")
    col_kelas = find_col(
        df_beban_raw, ["Kelas", "Nama_Kelas", "Rombel"], "Kelas"
    )
    col_jw = find_col(
        df_beban_raw, ["Jam_Wajib", "Jam Wajib", "Target_Jam", "Jam"], "Jam_Wajib"
    )

    clean_records = []
    if not df_beban_raw.empty and col_guru in df_beban_raw.columns:
      last_guru = None
      for _, r in df_beban_raw.iterrows():
        g_val = force_str(r.get(col_guru))
        if g_val:
          last_guru = g_val
        else:
          g_val = last_guru
        k_val = force_str(r.get(col_kelas)).upper()
        jw_val = force_int(r.get(col_jw), 0)
        if g_val and k_val and jw_val > 0:
          clean_records.append(
              {"Guru": str(g_val), "Kelas": str(k_val), "Jam_Wajib": int(jw_val)}
          )

    if not clean_records:
      st.error("❌ Data Beban Mengajar (Guru_Kelas) kosong atau tidak valid!")
      st.stop()

    df_beban_clean = pd.DataFrame(clean_records)
    df_pair = df_beban_clean.groupby(["Guru", "Kelas"], as_index=False)[
        "Jam_Wajib"
    ].sum()

    GURU = sorted(list(set(str(force_str(g)) for g in df_pair["Guru"])))
    KELAS = sorted(list(set(str(force_str(k)) for k in df_pair["Kelas"])))

    valid_gk_pairs = []
    for _, row in df_pair.iterrows():
      g_i = str(force_str(row["Guru"]))
      k_i = str(force_str(row["Kelas"]))
      jw_i = int(force_int(row["Jam_Wajib"]))
      if g_i and k_i and jw_i > 0:
        valid_gk_pairs.append((g_i, k_i))

    valid_gk_pairs = list(set(valid_gk_pairs))

    mgmp_teachers = set()
    for g in GURU:
      st_info = status_dict.get(str(g), {})
      val = force_str(st_info.get("Is_MGMP")).upper()
      if val in ["1", "1.0", "TRUE", "Y", "YES"]:
        mgmp_teachers.add(str(g))

    # Build PuLP Model
    model = pulp.LpProblem("Penjadwalan_SMPN2Plered_Streamlit", pulp.LpMinimize)

    var_keys = [
        (str(g), str(k), str(h), int(j))
        for (g, k) in valid_gk_pairs
        for h in HARI
        for j in JAM_HARI.get(str(h), [])
    ]
    pair_keys = [(str(g), str(k)) for (g, k) in valid_gk_pairs]
    c2_keys = [
        (str(k), str(h), int(j))
        for k in KELAS
        for h in HARI
        for j in JAM_HARI.get(str(h), [])
    ]
    dh_keys = [(str(g), str(h)) for g in GURU for h in HARI]

    gap_keys = []
    for g, k in valid_gk_pairs:
      sg, sk = str(g), str(k)
      for h in HARI:
        sh = str(h)
        j_list = JAM_HARI.get(sh, [])
        for idx in range(len(j_list) - 2):
          gap_keys.append((sg, sk, sh, int(j_list[idx])))

    # Create Decision Variables
    x = {
        (sg, sk, sh, sj): create_var(
            f"x_{safe_name(sg)}_{safe_name(sk)}_{safe_name(sh)}_{sj}",
            low_bound=0,
            up_bound=1,
            cat=pulp.LpBinary,
        )
        for (sg, sk, sh, sj) in var_keys
    }

    d_pair_minus = {
        (sg, sk): create_var(
            f"dp_minus_{safe_name(sg)}_{safe_name(sk)}",
            low_bound=0,
            cat=pulp.LpContinuous,
        )
        for (sg, sk) in pair_keys
    }

    d_pair_plus = {
        (sg, sk): create_var(
            f"dp_plus_{safe_name(sg)}_{safe_name(sk)}",
            low_bound=0,
            cat=pulp.LpContinuous,
        )
        for (sg, sk) in pair_keys
    }

    d_c2_minus = {
        (sk, sh, sj): create_var(
            f"dc2_minus_{safe_name(sk)}_{safe_name(sh)}_{sj}",
            low_bound=0,
            cat=pulp.LpContinuous,
        )
        for (sk, sh, sj) in c2_keys
    }

    d_h_plus = {
        (sg, sh): create_var(
            f"dh_plus_{safe_name(sg)}_{safe_name(sh)}",
            low_bound=0,
            cat=pulp.LpContinuous,
        )
        for (sg, sh) in dh_keys
    }

    d_h_minus = {
        (sg, sh): create_var(
            f"dh_minus_{safe_name(sg)}_{safe_name(sh)}",
            low_bound=0,
            cat=pulp.LpContinuous,
        )
        for (sg, sh) in dh_keys
    }

    z_gap = {
        (sg, sk, sh, sj): create_var(
            f"zgap_{safe_name(sg)}_{safe_name(sk)}_{safe_name(sh)}_{sj}",
            low_bound=0,
            cat=pulp.LpContinuous,
        )
        for (sg, sk, sh, sj) in gap_keys
    }

    # Constraints
    for g in mgmp_teachers:
      sg = str(g)
      st_info = status_dict.get(sg, {})
      mapel_raw = force_str(st_info.get("Mata_Pelajaran"))
      mapel_list = [
          m.strip().upper() for m in mapel_raw.split(",") if m.strip()
      ]
      for m_name in mapel_list:
        h_mgmp = HARI_MGMP_MAPEL.get(m_name)
        if h_mgmp and h_mgmp in HARI:
          sh_mgmp = str(h_mgmp)
          assigned_k = [k_i for (g_i, k_i) in valid_gk_pairs if g_i == sg]
          for k_i in assigned_k:
            sk_i = str(k_i)
            for j in JAM_HARI.get(sh_mgmp, []):
              j_i = int(j)
              if j_i > 2 and (sg, sk_i, sh_mgmp, j_i) in x:
                model += x[(sg, sk_i, sh_mgmp, j_i)] == 0

    penalti_list = []

    for g in GURU:
      sg = str(g)
      assigned_k = [k_i for (g_i, k_i) in valid_gk_pairs if g_i == sg]
      if assigned_k:
        for h in HARI:
          sh = str(h)
          for j in JAM_HARI.get(sh, []):
            j_i = int(j)
            vars_for_hour = [
                x[(sg, str(k_i), sh, j_i)]
                for k_i in assigned_k
                if (sg, str(k_i), sh, j_i) in x
            ]
            if vars_for_hour:
              model += pulp.lpSum(vars_for_hour) <= 1

    for k in KELAS:
      sk = str(k)
      assigned_g = [g_i for (g_i, k_i) in valid_gk_pairs if k_i == sk]
      if assigned_g:
        for h in HARI:
          sh = str(h)
          for j in JAM_HARI.get(sh, []):
            j_i = int(j)
            if (sk, sh, j_i) in d_c2_minus:
              vars_for_class = [
                  x[(str(g_i), sk, sh, j_i)]
                  for g_i in assigned_g
                  if (str(g_i), sk, sh, j_i) in x
              ]
              model += (
                  pulp.lpSum(vars_for_class) + d_c2_minus[(sk, sh, j_i)] == 1
              )

    for _, row in df_pair.iterrows():
      g, k, jw = (
          str(force_str(row["Guru"])),
          str(force_str(row["Kelas"])),
          int(force_int(row["Jam_Wajib"])),
      )
      if (g, k) in d_pair_minus and (g, k) in d_pair_plus:
        vars_for_pair = [
            x[(g, k, str(h), int(j))]
            for h in HARI
            for j in JAM_HARI.get(str(h), [])
            if (g, k, str(h), int(j)) in x
        ]
        model += (
            pulp.lpSum(vars_for_pair)
            + d_pair_minus[(g, k)]
            - d_pair_plus[(g, k)]
            == jw
        )

    for g, k in valid_gk_pairs:
      sg, sk = str(g), str(k)
      for h in HARI:
        sh = str(h)
        j_list = JAM_HARI.get(sh, [])
        for idx in range(len(j_list) - 2):
          j1, j2, j3 = (
              int(j_list[idx]),
              int(j_list[idx + 1]),
              int(j_list[idx + 2]),
          )
          if (
              (sg, sk, sh, j1) in x
              and (sg, sk, sh, j2) in x
              and (sg, sk, sh, j3) in x
              and (sg, sk, sh, j1) in z_gap
          ):
            model += (
                x[(sg, sk, sh, j1)]
                + x[(sg, sk, sh, j3)]
                - x[(sg, sk, sh, j2)]
                - z_gap[(sg, sk, sh, j1)]
                <= 1
            )

    for g in GURU:
      sg = str(g)
      st_info = status_dict.get(sg, {})
      is_wali_val = force_str(st_info.get("Is_Wali")).upper()
      if is_wali_val in ["1", "1.0", "TRUE", "Y", "YES"]:
        k_wali = str(force_str(st_info.get("Kelas_Wali"))).upper()
        if (
            (sg, k_wali) in valid_gk_pairs
            and "Jumat" in HARI
            and (sg, k_wali, "Jumat", 1) in x
        ):
          p_c6 = create_var(
              f"penalti_wali_{safe_name(sg)}",
              low_bound=0,
              cat=pulp.LpContinuous,
          )
          penalti_list.append(p_c6)
          model += x[(sg, k_wali, "Jumat", 1)] + p_c6 >= 1

    wakasek_teachers = [
        str(g)
        for g in GURU
        if force_str(status_dict.get(str(g), {}).get("Is_Wakasek")).upper()
        in ["1", "1.0", "TRUE", "Y", "YES"]
    ]
    if wakasek_teachers:
      for h in HARI:
        sh = str(h)
        wakasek_vars = [
            x[(g_w, str(k_i), sh, 1)]
            for g_w in wakasek_teachers
            for k_i in KELAS
            if (g_w, str(k_i), sh, 1) in x
        ]
        if wakasek_vars:
          model += pulp.lpSum(wakasek_vars) <= 1

    for g in GURU:
      sg = str(g)
      is_pjok_val = force_str(status_dict.get(sg, {}).get("Is_PJOK")).upper()
      if is_pjok_val in ["1", "1.0", "TRUE", "Y", "YES"]:
        assigned_k = [k_i for (g_i, k_i) in valid_gk_pairs if g_i == sg]
        for h in HARI:
          sh = str(h)
          for k_i in assigned_k:
            sk_i = str(k_i)
            for j in JAM_HARI.get(sh, []):
              j_i = int(j)
              if j_i > 4 and (sg, sk_i, sh, j_i) in x:
                p_c8 = create_var(
                    f"penalti_pjok_{safe_name(sg)}_{safe_name(sh)}_{safe_name(sk_i)}_{j_i}",
                    low_bound=0,
                    cat=pulp.LpContinuous,
                )
                penalti_list.append(p_c8)
                model += x[(sg, sk_i, sh, j_i)] - p_c8 <= 0

    model += (
        100000.0
        * pulp.lpSum([d_pair_minus[key] + d_pair_plus[key] for key in pair_keys])
        + 10000.0 * pulp.lpSum([d_c2_minus[key] for key in c2_keys])
        + 50000.0 * pulp.lpSum([z_gap[key] for key in gap_keys])
        + 1000.0 * pulp.lpSum(penalti_list)
        + 2.0 * pulp.lpSum([d_h_plus[key] + d_h_minus[key] for key in dh_keys])
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
