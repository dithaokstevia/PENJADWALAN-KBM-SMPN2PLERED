"""
================================================================================
SKRIP OPTIMASI PENJADWALAN GURU DINAMIS (SMPN 2 PLERED)
Model: Binary Integer Programming (BIP 0-1) & Goal Programming
Membaca 4 Sheet Dinamis dari file 'data_jadwal(1).xlsx'
================================================================================
"""

import os
import pandas as pd
import pulp

def jalankan_optimasi_dinamis(excel_input_path='data_jadwal(1).xlsx', excel_output_path='Jadwal_Guru_SMPN2Plered.xlsx'):
    print("==================================================================")
    print("   PROSES OPTIMASI JADWAL DINAMIS (FULL CONFIGURABLE MODEL)      ")
    print("==================================================================")
    
    if not os.path.exists(excel_input_path):
        print(f"❌ ERROR: File '{excel_input_path}' tidak ditemukan!")
        print(f"Pastikan file '{excel_input_path}' sudah ada di folder / repositori.")
        return

    print(f"\n1. Membaca data 4 sheet dari file '{excel_input_path}'...")
    df_config = pd.read_excel(excel_input_path, sheet_name='Config_Sekolah')
    df_mgmp_rule = pd.read_excel(excel_input_path, sheet_name='Aturan_MGMP')
    df_status_raw = pd.read_excel(excel_input_path, sheet_name='Status_Guru')
    df_beban_raw = pd.read_excel(excel_input_path, sheet_name='Guru_Kelas')

    # Penanganan Merged Cells di sheet Guru_Kelas (Forward Fill)
    df_beban_raw['Guru'] = df_beban_raw['Guru'].replace(r'^\s*$', None, regex=True).ffill()
    df_beban_raw['Guru'] = df_beban_raw['Guru'].astype(str).str.strip()
    df_beban_raw['Kelas'] = df_beban_raw['Kelas'].astype(str).str.strip().str.upper()
    df_beban_raw['Jam_Wajib'] = pd.to_numeric(df_beban_raw['Jam_Wajib'], errors='coerce').fillna(0).astype(int)

    INVALID_TEXTS = ['NAN', 'NONE', '', 'NULL', 'GURU', 'KELAS', 'UNNAMED: 0']
    df_beban = df_beban_raw[
        (~df_beban_raw['Guru'].str.upper().isin(INVALID_TEXTS)) & 
        (~df_beban_raw['Kelas'].isin(INVALID_TEXTS)) & 
        (df_beban_raw['Jam_Wajib'] > 0)
    ].copy()
    
    df_status_raw['Guru'] = df_status_raw['Guru'].astype(str).str.strip()
    df_status = df_status_raw[~df_status_raw['Guru'].str.upper().isin(INVALID_TEXTS)].drop_duplicates(subset=['Guru']).copy()
    df_pair = df_beban.groupby(['Guru', 'Kelas'], as_index=False)['Jam_Wajib'].sum()

    # Membaca Format Hari & Jam KBM Dinamis dari Config_Sekolah
    HARI = list(df_config['Hari'].astype(str).str.strip())
    JAM_HARI = {}
    for _, r in df_config.iterrows():
        h_name = str(r['Hari']).strip()
        j_count = int(r['Jumlah_Jam_KBM'])
        JAM_HARI[h_name] = list(range(1, j_count + 1))

    # Membaca Pemetaan Hari MGMP dari Aturan_MGMP
    HARI_MGMP_MAPEL = dict(zip(
        df_mgmp_rule['Mata_Pelajaran'].astype(str).str.strip().str.upper(),
        df_mgmp_rule['Hari_MGMP'].astype(str).str.strip()
    ))

    GURU = sorted(list(df_pair['Guru'].unique()))
    KELAS = sorted(list(df_pair['Kelas'].unique()))
    status_dict = df_status.set_index('Guru').to_dict('index')
    valid_gk_pairs = set((row['Guru'], row['Kelas']) for _, row in df_pair.iterrows() if row['Jam_Wajib'] > 0)

    # Identifikasi Guru Perwakilan MGMP Terdaftar
    mgmp_teachers = set()
    for g in GURU:
        st = status_dict.get(g, {})
        val = st.get('Is_MGMP')
        if pd.notna(val) and str(val).strip().upper() in ['1', '1.0', 'TRUE', 'Y', 'YES']:
            mgmp_teachers.add(g)

    print(f"Data Terbaca: {len(GURU)} Guru, {len(KELAS)} Kelas, {len(HARI)} Hari KBM.")
    print(f"Ditemukan {len(mgmp_teachers)} Guru perwakilan MGMP.")

    # 2. Membangun Model Optimasi PuLP
    print("\n2. Membangun model matematika BIP 0-1 PuLP...")
    model = pulp.LpProblem("Penjadwalan_SMPN2Plered_Dinamis", pulp.LpMinimize)

    var_keys = [(g, k, h, j) for (g, k) in valid_gk_pairs for h in HARI for j in JAM_HARI[h]]
    x = pulp.LpVariable.dicts("x", var_keys, cat=pulp.LpBinary)

    pair_keys = [(row['Guru'], row['Kelas']) for _, row in df_pair.iterrows()]
    d_pair_minus = pulp.LpVariable.dicts("dpair_minus", pair_keys, lowBound=0)
    d_pair_plus = pulp.LpVariable.dicts("dpair_plus", pair_keys, lowBound=0)

    c2_keys = [(k, h, j) for k in KELAS for h in HARI for j in JAM_HARI[h]]
    d_c2_minus = pulp.LpVariable.dicts("dc2_minus", c2_keys, lowBound=0)

    dh_keys = [(g, h) for g in GURU for h in HARI]
    d_h_plus = pulp.LpVariable.dicts("dh_plus", dh_keys, lowBound=0)
    d_h_minus = pulp.LpVariable.dicts("dh_minus", dh_keys, lowBound=0)

    # Variabel Block Teaching (Pencegahan Gap Jam Mengajar)
    gap_keys = []
    for (g, k) in valid_gk_pairs:
        for h in HARI:
            j_list = JAM_HARI[h]
            for idx in range(len(j_list) - 2):
                gap_keys.append((g, k, h, j_list[idx]))
    z_gap = pulp.LpVariable.dicts("z_gap", gap_keys, lowBound=0)

    # Aturan MGMP Terdaftar: Jam > 2 Dikosongkan pada Hari MGMP Mapelnya
    for g in mgmp_teachers:
        st = status_dict.get(g, {})
        mapel_raw = str(st.get('Mata_Pelajaran', ''))
        mapel_list = [m.strip().upper() for m in mapel_raw.split(',') if m.strip()]
        
        for m_name in mapel_list:
            h_mgmp = HARI_MGMP_MAPEL.get(m_name)
            if h_mgmp and h_mgmp in HARI:
                assigned_k = [k for (g_i, k) in valid_gk_pairs if g_i == g]
                for k in assigned_k:
                    for j in JAM_HARI[h_mgmp]:
                        if j > 2:
                            model += x[g, k, h_mgmp, j] == 0

    penalti_list = []

    # C1: Maksimal 1 Kelas per Guru per Jam
    for g in GURU:
        assigned_k = [k for (g_i, k) in valid_gk_pairs if g_i == g]
        if assigned_k:
            for h in HARI:
                for j in JAM_HARI[h]:
                    model += pulp.lpSum([x[g, k, h, j] for k in assigned_k]) <= 1

    # C2: Tepat 1 Guru per Kelas per Jam (31 Jam/Minggu)
    for k in KELAS:
        assigned_g = [g for (g, k_i) in valid_gk_pairs if k_i == k]
        if assigned_g:
            for h in HARI:
                for j in JAM_HARI[h]:
                    model += pulp.lpSum([x[g, k, h, j] for g in assigned_g]) + d_c2_minus[k, h, j] == 1

    # C3: Target Jam Wajib (Guru, Kelas)
    for _, row in df_pair.iterrows():
        g, k, jw = row['Guru'], row['Kelas'], row['Jam_Wajib']
        model += (
            pulp.lpSum([x[g, k, h, j] for h in HARI for j in JAM_HARI[h]]) 
            + d_pair_minus[g, k] - d_pair_plus[g, k] == jw
        )

    # C4: Block Teaching Tanpa Jeda Jam (Jam Berdampingan Kontinu)
    for (g, k) in valid_gk_pairs:
        for h in HARI:
            j_list = JAM_HARI[h]
            for idx in range(len(j_list) - 2):
                j1, j2, j3 = j_list[idx], j_list[idx+1], j_list[idx+2]
                model += x[g, k, h, j1] + x[g, k, h, j3] - x[g, k, h, j2] - z_gap[g, k, h, j1] <= 1

    # Aturan Wali Kelas (Jumat Jam 1 di Kelas Bimbingannya)
    for g in GURU:
        st = status_dict.get(g, {})
        is_wali_val = st.get('Is_Wali')
        if pd.notna(is_wali_val) and str(is_wali_val).strip().upper() in ['1', '1.0', 'TRUE', 'Y', 'YES']:
            if pd.notna(st.get('Kelas_Wali')):
                k_wali = str(st.get('Kelas_Wali')).strip().upper()
                if (g, k_wali) in valid_gk_pairs and 'Jumat' in HARI:
                    p_c6 = pulp.LpVariable(f"penalti_wali_{g}", lowBound=0)
                    penalti_list.append(p_c6)
                    model += x[g, k_wali, 'Jumat', 1] + p_c6 >= 1

    # Aturan Wakasek Bergantian Mengajar Jam 1
    wakasek_teachers = [
        g for g in GURU 
        if pd.notna(status_dict.get(g, {}).get('Is_Wakasek')) and 
        str(status_dict.get(g, {}).get('Is_Wakasek')).strip().upper() in ['1', '1.0', 'TRUE', 'Y', 'YES']
    ]
    if wakasek_teachers:
        for h in HARI:
            model += pulp.lpSum([x[g_w, k, h, 1] for g_w in wakasek_teachers for k in valid_gk_pairs if (g_w, k) in valid_gk_pairs]) <= 1

    # Aturan PJOK Khusus Jam 1 s.d. 4
    for g in GURU:
        is_pjok_val = status_dict.get(g, {}).get('Is_PJOK')
        if pd.notna(is_pjok_val) and str(is_pjok_val).strip().upper() in ['1', '1.0', 'TRUE', 'Y', 'YES']:
            assigned_k = [k for (g_i, k) in valid_gk_pairs if g_i == g]
            for h in HARI:
                for k in assigned_k:
                    for j in JAM_HARI[h]:
                        if j > 4:
                            p_c8 = pulp.LpVariable(f"penalti_pjok_{g}_{h}_{k}_{j}", lowBound=0)
                            penalti_list.append(p_c8)
                            model += x[g, k, h, j] - p_c8 <= 0

    # FUNGSI TUJUAN (Minimasi Total Penalti / Deviasi)
    model += (
        100000.0 * pulp.lpSum([d_pair_minus[g, k] + d_pair_plus[g, k] for g, k in pair_keys])
        + 10000.0 * pulp.lpSum([d_c2_minus[k, h, j] for k, h, j in c2_keys])
        + 50000.0 * pulp.lpSum([z_gap[key] for key in gap_keys])
        + 1000.0 * pulp.lpSum(penalti_list)
        + 2.0 * pulp.lpSum([d_h_plus[g, h] + d_h_minus[g, h] for g in GURU for h in HARI])
    )

    # 3. Mengeksekusi Solver CBC
    print("3. Mengeksekusi Solver CBC (Branch-and-Bound)...")
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=60, gapRel=0.0)
    model.solve(solver)

    if model.status in [pulp.LpStatusOptimal, 1]:
        records = []
        for (g, k, h, j), var in x.items():
            if var.varValue and var.varValue > 0.5:
                records.append({'Hari': h, 'Jam_Ke': j, 'Kelas': k, 'Guru': g})
                
        df_hasil = pd.DataFrame(records)
        df_hasil.sort_values(by=['Hari', 'Jam_Ke', 'Kelas'], inplace=True)
        
        with pd.ExcelWriter(excel_output_path, engine='openpyxl') as writer:
            df_hasil.to_excel(writer, sheet_name='Data_Penugasan', index=False)
            pivot_kelas = df_hasil.pivot(index=['Hari', 'Jam_Ke'], columns='Kelas', values='Guru').fillna('-')
            pivot_kelas.to_excel(writer, sheet_name='Jadwal_per_Kelas')
            pivot_guru = df_hasil.pivot(index=['Hari', 'Jam_Ke'], columns='Guru', values='Kelas').fillna('-')
            pivot_guru.to_excel(writer, sheet_name='Jadwal_per_Guru')
            
        print(f"\n✅ SUCCESS: File Output Jadwal berhasil disimpan ke '{excel_output_path}'")

if __name__ == '__main__':
    jalankan_optimasi_dinamis(excel_input_path='data_jadwal(1).xlsx')
