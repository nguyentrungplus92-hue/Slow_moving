from pyrfc import Connection, ABAPApplicationError, ABAPRuntimeError, LogonError, CommunicationError
import time
class SAPTableReader:
    def __init__(self, ashost, sysnr, client, user, passwd, batch_size=15, delimiter='|'):
        self.conn = Connection(ashost=ashost, sysnr=sysnr, client=client, user=user, passwd=passwd)
        self.batch_size = batch_size
        self.delimiter = delimiter

    def chunk_list(self, lst):
        """Chia list lst thành các đoạn nhỏ mỗi đoạn tối đa batch_size phần tử."""
        for i in range(0, len(lst), self.batch_size):
            yield lst[i:i+self.batch_size]

    def parse_data(self, data_rows, field_names):
        """Chuyển list các dict {'WA': 'val1|val2|...'} thành list dict theo field_names."""
        parsed = []
        for row in data_rows:
            values = row['WA'].split(self.delimiter)
            record = {field_names[i]: values[i] if i < len(values) else '' for i in range(len(field_names))}
            parsed.append(record)
        return parsed

    def read_table(self, query_table, fields_to_get, options=None):
        """
        Đọc dữ liệu từ bảng SAP theo batch từng phần trường, trả về list dict dữ liệu đầy đủ.
        """
        all_data = None
        all_fields = []

        for field_chunk in self.chunk_list(fields_to_get):
            field_list = [{'FIELDNAME': f} for f in field_chunk]

            result = self.conn.call(
                'RFC_READ_TABLE',
                QUERY_TABLE=query_table,
                DELIMITER=self.delimiter,
                FIELDS=field_list,
                OPTIONS=options or []
            )

            data_chunk = result['DATA']

            if all_data is None:
                all_data = data_chunk
                all_fields = field_chunk
            else:
                for i in range(len(all_data)):
                    all_data[i]['WA'] += self.delimiter + data_chunk[i]['WA']
                all_fields.extend(field_chunk)

        return self.parse_data(all_data, all_fields)

    def get_mkpf_data(self, from_date, to_date):
        """Lấy MKPF theo khoảng ngày Posting Date"""
        return self.read_table(
            query_table="MKPF",
            fields_to_get=["MBLNR", "MJAHR", "BUDAT", "USNAM"],
            options=[{"TEXT": f"BUDAT >= '{from_date}' AND BUDAT <= '{to_date}'"}]
        )

    def get_mseg_data(self, plant, year, movement_types):
        """Lấy MSEG theo Movement Type và năm"""
        mt_cond = " or ".join([f"BWART = '{mt}'" for mt in movement_types])
        return self.read_table(
            query_table="MSEG",
            fields_to_get=["MBLNR", "MJAHR", "WERKS", "BWART", "LIFNR", "MATNR", "MENGE"],
            options=[{"TEXT": f"( {mt_cond} ) and MJAHR = '{year}' and WERKS = '{plant}'"}]
        )

    def join_mkpf_mseg(self, mkpf_data, mseg_data):
        """Join MSEG với MKPF để thêm BUDAT và sắp xếp lại thứ tự field"""
        mkpf_map = {f"{row['MBLNR']}|{row['MJAHR']}": row['BUDAT'] for row in mkpf_data}
        joined = []
        for row in mseg_data:
            key = f"{row['MBLNR']}|{row['MJAHR']}"
            if key in mkpf_map:
                budat = mkpf_map[key]
                ordered_row = {
                    "MBLNR": row["MBLNR"],
                    "BUDAT": budat,
                    "MJAHR": row["MJAHR"],
                    'WERKS': row["WERKS"],
                    "BWART": row["BWART"],
                    'LIFNR': row['LIFNR'],
                    "MATNR": row["MATNR"],
                    "MENGE": row["MENGE"]
                }
                joined.append(ordered_row)
        return joined
    
#   GỌI BAPI_GOODSMVT_GETITEMS để lấy các giao dịch
    def get_goods_movement(self, movement_types, matnrs, plants, date_from, date_to):

        print(f"Lấy giao dịch cho thời gian: {date_from} - {date_to} ")
        # Build điều kiện Movement Type
        move_type_ra = [
            {"SIGN": "I", "OPTION": "EQ", "LOW": mt, "HIGH": ""}
            for mt in movement_types
        ]


        # Build điều kiện Matnr
        if matnrs == ['']:
            matnrs_ra =[]
        else:   
            matnrs_ra = [
                {"SIGN": "I", "OPTION": "EQ", "LOW": mt, "HIGH": ""}
                for mt in matnrs
            ]


        # Build điều kiện Plant
        if plants == ['']:
            plant_ra =[]
        else:   
            plant_ra = [
                {"SIGN": "I", "OPTION": "EQ", "LOW": mt, "HIGH": ""}
                for mt in plants
            ]
        

        # Build điều kiện Posting Date
        pstng_date_ra = [{
            "SIGN": "I", "OPTION": "BT", "LOW": date_from, "HIGH": date_to
        }]
        start = time.time()
        # Gọi BAPI
        result = self.conn.call(
            "BAPI_GOODSMVT_GETITEMS",
            MATERIAL_RA = matnrs_ra,
            PLANT_RA = plant_ra,
            MOVE_TYPE_RA=move_type_ra,
            PSTNG_DATE_RA=pstng_date_ra
        )

        headers = result.get('GOODSMVT_HEADER', [])
        items = result.get('GOODSMVT_ITEMS', [])

        # Chuyển header thành dict để tra nhanh
        header_map = {
            (h['MAT_DOC']): h['PSTNG_DATE'] for h in headers
        }

        # Ghép BUDAT vào từng item
        merged_data = []
        for item in items:
            key = (item['MAT_DOC'])
            budat = header_map.get(key, None)
            merged_data.append({
                'MBLNR': item['MAT_DOC'],
                'BUDAT': budat,
                'MJAHR': item['DOC_YEAR'],
                'WERKS': item['PLANT'],
                'BWART': item['MOVE_TYPE'],
                'LIFNR': item['VENDOR'],
                'XAUTO': item['X_AUTO_CRE'],
                'MATNR': item['MATERIAL'],
                'MENGE': item['ENTRY_QNT'],
                'ERFME': item['ENTRY_UOM']
            })
        # print(date_to ,len(merged_data))

        end = time.time()
        # print(date_to, end - start)
        return merged_data



# =======================
# CÁCH SỬ DỤNG
# =======================
if __name__ == "__main__":
    reader = SAPTableReader(
        ashost="10.209.11.76",
        sysnr="00",
        client="300",
        user="ITS-2015030",
        passwd="Trung1992",
        batch_size=15
    )
    start = time.time()
    fields_to_get = ['MANDT','MATNR','ERSDA','ERNAM','LAEDA','AENAM','VPSTA','PSTAT','LVORM','MTART',
'MBRSH','MATKL','BISMT','MEINS','BSTME','ZEINR','ZEIAR','ZEIVR','ZEIFO','AESZN',
'BLATT','BLANZ','FERTH','FORMT','GROES','WRKST','NORMT','LABOR','EKWSL','BRGEW',
'NTGEW','GEWEI','VOLUM','VOLEH','BEHVO','RAUBE','TEMPB','DISST','TRAGR','STOFF',
'SPART','KUNNR','EANNR','WESCH','BWVOR','BWSCL','SAISO','ETIAR','ETIFO','ENTAR',
'EAN11','NUMTP','LAENG','BREIT','HOEHE','MEABM','PRDHA','AEKLK','CADKZ','QMPUR',
'ERGEW','ERGEI','ERVOL','ERVOE','GEWTO','VOLTO','VABME','KZREV','KZKFG','XCHPF',
'VHART','FUELG','STFAK','MAGRV','BEGRU','DATAB','LIQDT','SAISJ','PLGTP','MLGUT',
'EXTWG','SATNR','ATTYP','KZKUP','KZNFM','PMATA','MSTAE','MSTAV','MSTDE','MSTDV',
'TAKLV','RBNRM','MHDRZ','MHDHB','MHDLP','INHME','INHAL','VPREH','ETIAG','INHBR',
'CMETH','CUOBF','KZUMW','KOSCH','SPROF','NRFHG','MFRPN','MFRNR','BMATN','MPROF',
'KZWSM','SAITY','PROFL','IHIVI','ILOOS','SERLV','KZGVH','XGCHP','KZEFF','COMPL',
'IPRKZ','RDMHD','PRZUS','MTPOS_MARA','BFLME','MATFI','CMREL','BBTYP','SLED_BBD',
'GTIN_VARIANT','GENNR','RMATP','GDS_RELEVANT','WEORA','HUTYP_DFLT','PILFERABLE',
'WHSTC','WHMATGR','HNDLCODE','HAZMAT','HUTYP','TARE_VAR','MAXC','MAXC_TOL','MAXL',
'MAXB','MAXH','MAXDIM_UOM','HERKL','MFRGR','QQTIME','QQTIMEUOM','QGRP','SERIAL',
'PS_SMARTFORM','LOGUNIT','CWQREL','CWQPROC','CWQTOLGR','/BEV1/LULEINH','/BEV1/LULDEGRP',
'/BEV1/NESTRUCCAT','/DSD/VC_GROUP','/VSO/R_TILT_IND','/VSO/R_STACK_IND','/VSO/R_BOT_IND',
'/VSO/R_TOP_IND','/VSO/R_STACK_NO','/VSO/R_PAL_IND','/VSO/R_PAL_OVR_D','/VSO/R_PAL_OVR_W',
'/VSO/R_PAL_B_HT','/VSO/R_PAL_MIN_H','/VSO/R_TOL_B_HT','/VSO/R_NO_P_GVH','/VSO/R_QUAN_UNIT',
'/VSO/R_KZGVH_IND','MCOND','RETDELC','LOGLEV_RETO','NSNID','IMATN','PICNUM','BSTAT',
'COLOR_ATINN','SIZE1_ATINN','SIZE2_ATINN','COLOR','SIZE1','SIZE2','FREE_CHAR','CARE_CODE',
'BRAND_ID','FIBER_CODE1','FIBER_PART1','FIBER_CODE2','FIBER_PART2','FIBER_CODE3','FIBER_PART3',
'FIBER_CODE4','FIBER_PART4','FIBER_CODE5','FIBER_PART5','FASHGRD','FASHGRD'
]
    list_material = []
    data_Mara = reader.read_table('MARA', fields_to_get, list_material)

    print(f"Tổng số bản ghi của MARA: {len(data_Mara)}")
        # In 10 dòng đầu
    for row in data_Mara[:1]:
        print(row)
    end = time.time()
    print('Tổng thời gian xử lý Mara:',end - start)

#     # Lấy MKPF và MSEG
#     # mkpf_data = reader.get_mkpf_data("20250101", "20251231")
#     # mseg_data = reader.get_mseg_data("VE01","2025", ["261", "102"])

#     # print(f"MKPF count: {len(mkpf_data)}")  
#     # print(f"MSEG count: {len(mseg_data)}")

#     # # Join dữ liệu
#     # final_result = reader.join_mkpf_mseg(mkpf_data, mseg_data)
#     # print(f"Final joined count: {len(final_result)}")

#     # # In 10 dòng đầu
#     # for row in final_result[:10]:
#     #     print(row)

# results = reader.get_goods_movement(['261', '262'],[''], ["V501","VB01"],"20250701","20250731")
# print("xong")