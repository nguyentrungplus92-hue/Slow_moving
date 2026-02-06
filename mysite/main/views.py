from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from datetime import datetime
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from . import valid, db_postgres, excel
from SAP import condition, constants, sap_reader
from collections import defaultdict
from django.views.decorators.csrf import csrf_exempt
from zoneinfo import ZoneInfo
from django.utils import timezone
from sap_odata_client import connect_sap_rfc, rfc_read_table_all,fetch_sap_odata_all

# Tạo Semaphore để giới hạn số request SAP đồng thời
semaphore = asyncio.Semaphore(6)


# === KHỞI TẠO SAP READER ===
def get_sap_reader():
    """Tạo SAP reader instance"""
    return sap_reader.SAPTableReader(
        constants.ASHOST,
        constants.SYSNR,
        constants.CLIENT,
        constants.USER,
        constants.PASSWD,
        batch_size=constants.BATCH_SIZE
    )


# === HÀM ĐỒNG BỘ - Chạy trong thread ===
def read_sap_data(reader_instance, table_name, fields, conditions):
    """
    Đọc dữ liệu từ SAP (I/O-bound operation)
    Chạy trong thread executor
    """
    print(f"Đang đọc bảng {table_name}...")
    result = reader_instance.read_table(table_name, fields, conditions)
    print(f"Đã đọc xong bảng {table_name}: {len(result)} bản ghi")
    return result


# === HÀM ASYNC - Wrapper cho read_sap_data ===
async def fetch_sap_table_async(reader_instance, table_name, fields, conditions, sem):
    async with sem:
        return await asyncio.to_thread(
            read_sap_data, reader_instance, table_name, fields, conditions
        )

# === HÀM ASYNC - Wrapper cho get_goods_movement ===
async def fetch_goods_movement_async(reader_instance, movement_types, matnrs, plants, date_from, date_to, sem):
    async with sem:
        return await asyncio.to_thread(
            reader_instance.get_goods_movement,
            movement_types, matnrs, plants, date_from, date_to
        )


def home(request):
    return render(request, 'home.html')

def FG(request):
    return render(request, 'home_FG.html')

@csrf_exempt
@require_http_methods(["POST"])
async def home_post(request):
    """
    Xử lý POST request từ form
    Đọc dữ liệu SAP và trả về file Excel
    """
    start = time.time()
    # Lấy dữ liệu từ form
    date = request.POST.get('date', '')
    material = request.POST.get('material', '')
    plant = request.POST.getlist('plant')
    sloc = request.POST.get('sloc', '')
    report_detail = request.POST.get('report_detail', '')
    report_summary = request.POST.get('report_summary', '')
    down_Radio = request.POST.get('down_Radio', '')
    serverPath = request.POST.get('serverPath', '')


    month_diff = valid.month_diff(date)  # Lấy ra số tháng chênh lệch so với tháng hiện tại
    # Format dữ liệu
    conv_date = valid.format_date(date)
    conv_material = valid.split_and_clean(material)
    # conv_plant = valid.split_and_clean(plant)
    conv_sloc = valid.split_and_clean(sloc)
    # print(down_Radio)
    # print(serverPath)
    try:

        # 2 semaphore độc lập
        sem_tbl = asyncio.Semaphore(6)   # bảng
        sem_mvt = asyncio.Semaphore(6)   # goods movement

        # Build điều kiện WHERE
        builder = condition.WhereConditionBuilder()
        
        
        list_material = builder.build_where_conditions(conv_material, column_name="MATNR")

        if plant == ['']:
            list_plant = None
        else:
            list_plant = builder.build_where_conditions(plant, column_name="WERKS")
        
        list_vendor = [{'TEXT': "( LIFNR <> '' )"}]
        PLSCN = [{'TEXT': "( PLSCN = '000' )"}]
        inventory = valid.build_inventory_conditions_split()


        #-------------Get điều kiện cho bảng ZTMA_MRP1-------------------------#
        ZTMA_MRP1_conditions = builder.merge_multiple_where_conditions(
            [list_material, list_vendor, PLSCN, inventory]
            # [list_material, list_vendor]
        )


        #-------------Get điều kiện cho bảng MARA-------------------------#
        MARA_conditions = builder.merge_multiple_where_conditions(
            [list_material]
        )


        #-------------Get điều kiện cho bảng MARC-------------------------#
        MARC_conditions = builder.merge_multiple_where_conditions(
            [list_material,list_plant]
        )


        #-------------Get điều kiện cho bảng ZTMA_MTDCSM-------------------------#
        date_month_1 = valid.last_day_previous_month(conv_date,1)[:6]
        last_month = [date_month_1]

        build_condition = builder.build_where_conditions(last_month, column_name="SPMON")

        ZTMA_MTDCSM_conditions = builder.merge_multiple_where_conditions(
            [build_condition,list_plant,list_material]
        )


        #-------------Get điều kiện cho bảng T001L-------------------------#
        cont = ['']
        build_condition = builder.build_where_conditions(cont, column_name="DISKZ")
        T001L_conditions = builder.merge_multiple_where_conditions([build_condition,list_plant])


        #-------------Get điều kiện cho bảng LFA1-------------------------#
        LFA1_conditions = builder.merge_multiple_where_conditions([list_vendor])
     
        # #-------------Get điều kiện cho bảng TVARVC-------------------------#
        TVARVC_conditions = [{'TEXT': "( NAME = 'RATE_JPY-USD' )"}]

        # Khởi tạo SAP reader
        reader_instance = get_sap_reader()



        if constants.Check_HANA == '':      # Đang làm việc với ECC
        
            # Chuẩn bị tasks
            tables_config = [
                {
                    'table_name': 'ZTMA_MRP1',                  # 0 Lấy dữ liệu cho bảng ZTMA_MRP1
                    'fields': constants.ZTMA_MRP1_FIELDS,
                    'conditions': ZTMA_MRP1_conditions
                },
                {
                    'table_name': 'MARC',                       # 1 Lấy dữ liệu cho bảng MARC
                    'fields': constants.MARC_FIELDS,
                    'conditions': MARC_conditions
                },

                {
                    'table_name': 'ZTMA_MTDCSM',                # 2 Lấy dữ liệu cho bảng ZTMA_MTDCSM
                    'fields': constants.ZTMA_MTDCSM_FIELDS,
                    'conditions': ZTMA_MTDCSM_conditions
                },
                {
                    'table_name': 'T001L',                      # 3 Lấy dữ liệu cho bảng T001L
                    'fields': constants.T001L_FIELDS,
                    'conditions': T001L_conditions
                },
                {
                    'table_name': 'TVARVC',                     # 4 Lấy dữ liệu cho bảng TVARVC
                    'fields': constants.TVARVC_FIELDS,
                    'conditions': TVARVC_conditions
                },
                {
                    'table_name': 'MARA',                       # 5 Lấy dữ liệu cho bảng MARA
                    'fields': constants.MARA_FIELDS,
                    'conditions': MARA_conditions
                },
                {
                    'table_name': 'LFA1',                       # 6 Lấy dữ liệu cho bảng LFA1
                    'fields': constants.LFA1_FIELDS,
                    'conditions': LFA1_conditions
                },
            ]
            
        else:                                                   # Đang làm việc với HANA sử dụng RFC để lấy dữ liệu các bảng, còn 2 bảng MARA và LFA1 sẽ dùng Odata

            # Lấy dữ liệu của bảng MARA
            all_MARA = fetch_sap_odata_all(
                    base_url="http://hana.cmcconsulting.vn:8012",
                    odata_root="/sap/opu/odata/sap/",
                    service_name="API_PRODUCT_SRV",
                    entity_set="A_Product",
                    key=None,
                    select= "Product, ExternalProductGroup",                        
                    filter_=None,
                    expand=None,
                    fmt="json",
                    username=constants.USER,
                    password=constants.PASSWD
            )
            print(f"Đã đọc xong bảng MARA: {len(all_MARA)} bản ghi")


            # Lấy dữ liệu của bảng LFA1
            all_LFA1 = fetch_sap_odata_all(
                    base_url="http://hana.cmcconsulting.vn:8012",
                    odata_root="/sap/opu/odata/sap/",
                    service_name="API_BUSINESS_PARTNER",
                    entity_set="A_Supplier",
                    key=None,
                    select= "Supplier, SupplierName",                        
                    filter_=None,
                    expand=None,
                    fmt="json",
                    username=constants.USER,
                    password=constants.PASSWD

            )
            print(f"Đã đọc xong bảng LFA1: {len(all_LFA1)} bản ghi")



            # Chuẩn bị tasks
            tables_config = [
                {
                    'table_name': 'ZTMA_MRP1',                  # 0 Lấy dữ liệu cho bảng ZTMA_MRP1
                    'fields': constants.ZTMA_MRP1_FIELDS,
                    'conditions': ZTMA_MRP1_conditions
                },
                {
                    'table_name': 'MARC',                       # 1 Lấy dữ liệu cho bảng MARC
                    'fields': constants.MARC_FIELDS,
                    'conditions': MARC_conditions
                },

                {
                    'table_name': 'ZTMA_MTDCSM',                # 2 Lấy dữ liệu cho bảng ZTMA_MTDCSM
                    'fields': constants.ZTMA_MTDCSM_FIELDS,
                    'conditions': ZTMA_MTDCSM_conditions
                },
                {
                    'table_name': 'T001L',                      # 3 Lấy dữ liệu cho bảng T001L
                    'fields': constants.T001L_FIELDS,
                    'conditions': T001L_conditions
                },
                {
                    'table_name': 'TVARVC',                     # 4 Lấy dữ liệu cho bảng TVARVC
                    'fields': constants.TVARVC_FIELDS,
                    'conditions': TVARVC_conditions
                }
            ]

        # Chạy async - đọc dữ liệu SAP song parallel
        with ThreadPoolExecutor(max_workers=6) as executor:
            tasks = [
                fetch_sap_table_async(
                    reader_instance,
                    cfg['table_name'],
                    cfg['fields'],
                    cfg['conditions'],
                    sem_tbl
                )
                for cfg in tables_config
            ]
            results = await asyncio.gather(*tasks)

        
        RATE_JPY_USD = float(results[4][0]['LOW'])




        print('============================================================')


        

        # Lấy các giao dịch tháng n-1 từ SAP
        mvt = ["101", "102", "122", "123","309", "310","261", "262"]


        new_month_n_1, end_month_n_1 = valid.start_end_date(conv_date, 1, 1)
        date_range = valid.split_date_range(new_month_n_1, end_month_n_1, step_days=6)  
        # print(date_range)
        # Chạy async - đọc dữ liệu SAP song parallel
        with ThreadPoolExecutor(max_workers=3) as executor :
            tasks_mvt = [
                fetch_goods_movement_async(
                        reader_instance ,
                        mvt,
                        conv_material,
                        plant,
                        valid.format_date(rs[0]),       # From
                        valid.format_date(rs[1]),       # To
                        sem_mvt 
                    )
                for rs in date_range
            ]
            results_mvt2 = await asyncio.gather(*tasks_mvt)

        # Gộp tất cả kết quả lại thành một list duy nhất
        results_mvt = [item for sublist in results_mvt2 for item in sublist]
        print('Tổng số bản giao dịch lấy được từ SAP:',len(results_mvt))

        # Lấy các giao dịch từ tháng n-2 đến n-26 trong PostgreSQL. Chú ý: Các giao dịch này đa xử lý
        end_month_2 = valid.format_date2(valid.last_day_previous_month(conv_date,2))
        # end_month_2 = valid.format_date2(end_month_2)
        firt_month_2 = end_month_2[:8] + '01'

        end_month_7 = valid.format_date2(valid.last_day_previous_month(conv_date,7))
        firt_month_7 = end_month_7[:8] + '01'

        end_month_36 = valid.format_date2(valid.last_day_previous_month(conv_date,36))
        firt_month_36 = end_month_36[:8] + '01'


        functions_config = [
            {
                'name': 'fn_matnr_mvt_261_262_mv',
                'start_date': firt_month_7,
                'end_date': end_month_2     # Q1
            },
            {
                'name': 'fn_matnr_mvt_101_102_122_123_mv',
                'start_date': firt_month_36,
                'end_date': end_month_2     # Q2
            },
            {
                'name': 'fn_matnr_mvt_309_310_mv',
                'start_date': firt_month_36,
                'end_date': end_month_2     # Q3
            }
        ]

        # results_sql = asyncio.run(db_postgres.call_material_movement_functions(
        results_sql = await db_postgres.call_material_movement_functions(
            functions_config,
            matnrs=conv_material,
            plants=plant
        )
        # )
        # print(results_sql[0]['data'])

        # Xử lý dữ liệu

        result_detail = []             # chi tiết
        result_summary = []            # tóm tắt


        if constants.Check_HANA  == '':
            # Convert data_lfa1 thành dict để tra cứu nhanh-> Chú ý: Dữ liệu không được bị trùng
            lfa1_dict = {item['LIFNR']: item['NAME1'] for item in results[6]}
            # Convert data_Mara thành dict để tra cứu nhanh-> Chú ý: Dữ liệu không được bị trùng
            mara_dict = {item['MATNR']: item['EXTWG'] for item in results[5]}
        else:
            # Convert data_lfa1 thành dict để tra cứu nhanh-> Chú ý: Dữ liệu không được bị trùng
            lfa1_dict = {item['LIFNR']: item['NAME1'] for item in all_LFA1} 
            # Convert data_Mara thành dict để tra cứu nhanh-> Chú ý: Dữ liệu không được bị trùng
            mara_dict = {item['MATNR']: item['EXTWG'] for item in all_MARA}


        # Convert data_Marc -> dict, key là tuple (MATNR, WERKS)-> Chú ý: Dữ liệu không được bị trùng
        marc_dict = {(item['MATNR'], item['WERKS']): item for item in results[1]}

        # Convert T001L -> dict, key là tuple (WERKS, LGORT)-> Chú ý: Dữ liệu không được bị trùng
        T001L_dict = {(item['WERKS'], item['LGORT']): item for item in results[3]}


        # 1️⃣ Gom nhóm theo key - data_ZTMA_MTDCSM
        ZTMA_MTDCSM_dict = defaultdict(list)
        for item in results[2]:
            key = (item["MATNR"], item["WERKS"])
            ZTMA_MTDCSM_dict[key].append(item)


        # data_ZTMA_MRP1 = results[0]
        data_ZTMA_MRP1 = []

        SUM_FIELDS = [
            'MNG01','MNG02','MNG03','MNG04','MNG05','MNG06','MNG07','MNG08','MNG09',
            'MNG010','MNG011','MNG012','MNG013','MNG014','MNG015',
            'MNGPR01','MNGPR02','MNGPR03','MNGPR04','MNGPR05','MNGPR06','MNGPR07',
            'MNGPR08','MNGPR09','MNGPR010','MNGPR011','MNGPR012','MNGPR013','MNGPR014','MNGPR015',
            'MNGRQ01','MNGRQ02','MNGRQ03','MNGRQ04','MNGRQ05','MNGRQ06','MNGRQ07',
            'MNGRQ08','MNGRQ09','MNGRQ010','MNGRQ011','MNGRQ012','MNGRQ013','MNGRQ14','MNGRQ015'
        ]

        result_map = {}

        # Bước 1: Gom nhóm và tính tổng
        for item in results[0]:
            key = (item["MATNR"], item["WERKS"])

            if key not in result_map:
                result_map[key] = {
                    "base": None,
                    "sum": {f: 0.0 for f in SUM_FIELDS}
                }

            grp = result_map[key]

            for f in SUM_FIELDS:
                grp["sum"][f] += valid.convert_to_float(item.get(f))

            if item.get("LIFNR") == item.get("LIFNR_S"):
                grp["base"] = item

        # Bước 2: Tạo kết quả (TÁCH RIÊNG khỏi vòng lặp trên)
        for key, grp in result_map.items():
            base = grp["base"]
            if not base:
                continue

            rec = base.copy()
            for f, v in grp["sum"].items():
                rec[f] = round(v, 3)

            data_ZTMA_MRP1.append(rec)
        print('Dữ liệu sau khi gộp', len(data_ZTMA_MRP1))
        
        # 1️⃣ Gom nhóm theo key - data_ZTMA_MRP1
        ZTMA_MRP1_dict = defaultdict(list)
        # for item in [x for x in data_ZTMA_MRP1 if x["WERKS"] not in plant]:
        for item in data_ZTMA_MRP1:
            key = (item["MATNR"], item["LIFNR"])
            ZTMA_MRP1_dict[key].append(item)
        print(len(ZTMA_MRP1_dict))
 

        # 1️⃣ Gom nhóm theo key - results_mvt
        results_mvt_dict = defaultdict(list)
        for item in results_mvt:
            key = (item["MATNR"], item["WERKS"])
            results_mvt_dict[key].append(item)


        # 1️⃣ Gom nhóm theo key - fn_matnr_mvt_261_262
        mvt_261_dict = defaultdict(list)
        for item in results_sql[0]['data']:
            key = (item["matnr"].strip(), item["werks_d"].strip())
            mvt_261_dict[key].append(item)


        # 1️⃣ Gom nhóm theo key - fn_matnr_mvt_101_102_122_123
        mvt_101_dict = defaultdict(list)
        for item in results_sql[1]['data']:
            key = (item["matnr"].strip(), item["werks_d"].strip())
            mvt_101_dict[key].append(item)

        # 1️⃣ Gom nhóm theo key - fn_matnr_mvt_309_310
        mvt_309_dict = defaultdict(list)
        for item in results_sql[2]['data']:
            key = (item["matnr"].strip(), item["werks_d"].strip())
            mvt_309_dict[key].append(item)

        # print(mvt_101_dict)
        # for item in data_ZTMA_MRP1:
        # for item in [x for x in data_ZTMA_MRP1 if x["WERKS"] in plant]:

        for item in (data_ZTMA_MRP1 if not plant else [x for x in data_ZTMA_MRP1 if x["WERKS"] in plant]):
            
            # Tính Type 2 -> Cột C
            EXTWG = ''
            matnr = item["MATNR"]
            if item["MATNR"] in mara_dict:
                EXTWG = mara_dict[matnr ]

            # Tính NAME1 -> Cột J
            lifnr = item["LIFNR"]
            NAME1 = ''

            if lifnr in lfa1_dict:
                NAME1 = lfa1_dict[lifnr ]

            # Tính Std Price -> Cột K
            STD_PRICE = valid.calculate_std_price(item["STPRS"], item["PEINH"], 5)

            # Tính Net price -> Cột L
            
            if item["BPRME"].strip() == 'KG':
                item["PEINH_I"] = float(item["PEINH_I"]) * 1000
                item["BPRME"] = 'G'

            NET_PRICE = valid.calculate_std_price(item["NETPR"], item["PEINH_I"], 5) 

            if item["WAERS"].strip() == 'JPY':                  # Trường hợp với tiền tệ là JPY-> chuyển về USD
                NET_PRICE = NET_PRICE / RATE_JPY_USD
                item["WAERS"] = 'USD'  # cập nhật giá trị

            # Tính MMSTA, BSTRF, BSTMI, LGFSB của MARC  -> Cột N,O,P,Q
            key = (item['MATNR'], item['WERKS'])                #Tạo Key để tra cứu
            if key in marc_dict:
                marc_item = marc_dict[key]

                BESKZ = marc_item["BESKZ"].strip()
                DISMM = marc_item["DISMM"].strip()
                # print(marc_item)
                # ❌ Nếu procurement type khác 'F' or MRP type = 'ND' thì bỏ record này 
                if BESKZ != "F" or DISMM == 'ND':
                    continue

                MMSTA = marc_item["MMSTA"]
                BSTRF = marc_item["BSTRF"]
                BSTMI = marc_item["BSTMI"]
                LGFSB = marc_item["LGFSB"]
            else:
                continue
                MMSTA = ''
                BSTRF = ''
                BSTMI = ''
                LGFSB = ''

            if LGFSB not in conv_sloc and len(conv_sloc) > 0:
                continue

            # Tính tổng Total PO, RO, PR, requirement -> Cột R,S,T,U
            PO_values = [
                item['MNG01'], item['MNG02'], item['MNG03'], item['MNG04'], item['MNG05'],
                item['MNG06'], item['MNG07'], item['MNG08'], item['MNG09'], item['MNG010'],
                item['MNG011'], item['MNG012'], item['MNG013'], item['MNG014'], item['MNG015']
            ]

            SUM_PO = valid.sum_cal(PO_values,2,month_diff)


            SUM_RO = ''

            PR_values = [
                item['MNGPR01'], item['MNGPR02'], item['MNGPR03'], item['MNGPR04'], item['MNGPR05'],
                item['MNGPR06'], item['MNGPR07'], item['MNGPR08'], item['MNGPR09'], item['MNGPR010'],
                item['MNGPR011'], item['MNGPR012'], item['MNGPR013'], item['MNGPR014'], item['MNGPR015']
            ]
            SUM_PR = valid.sum_cal(PR_values,2,month_diff)

            RQ_values = [
                item['MNGRQ01'], item['MNGRQ02'], item['MNGRQ03'], item['MNGRQ04'], item['MNGRQ05'],
                item['MNGRQ06'], item['MNGRQ07'], item['MNGRQ08'], item['MNGRQ09'], item['MNGRQ010'],
                item['MNGRQ011'], item['MNGRQ012'], item['MNGRQ013'], item['MNGRQ14'], item['MNGRQ015']
            ]
            SUM_RQ = valid.sum_cal(RQ_values,2,month_diff)

            # Phân loại Discont -> Cột V
            DISCON = valid.check_discon(item["FKGRP"])

            # Tính End_Stock_Month-1, Amt AC, Amt ST -> Cột W, X, Y
            total = 0.00
            key = (item['MATNR'], item['WERKS'])                #Tạo Key để tra cứu
            for i in ZTMA_MTDCSM_dict[key]:
                if(i['WERKS'], i['LGORT']) in T001L_dict or i['LIFNR'].strip() != '' :
                    UMLMD_L = i["UMLMD_L"].strip()
                    LABST_P = i["LABST_P"].strip()
                    INSME_P = i["INSME_P"].strip()
                    total += float(UMLMD_L) + float(LABST_P) + float(INSME_P)

            # Tính tồn kho tháng n-Futuret trường hợp user nhập tương lai
            total += valid.sum_cal_next(PO_values,2,month_diff) + valid.sum_cal_next(PR_values,2,month_diff) + valid.sum_cal_next(RQ_values,2,month_diff)
            Amt_AC = total * float(NET_PRICE)
            Amt_ST = total * float(STD_PRICE)


            key = (item['MATNR'].strip(), item['WERKS'].strip())

            total_309_n_1 = 0.00
            total_101_n_1 = 0.00
            total_309_n_1_3 = 0.00
            total_101_n_1_3 = 0.00
            total_309_n_4_6 = 0.00
            total_101_n_4_6 = 0.00
            total_309_n_7_12 = 0.00
            total_101_n_7_12 = 0.00
            total_309_n_13_24 = 0.00
            total_101_n_13_24 = 0.00
            total_309_n_25_36 = 0.00
            total_101_n_25_36 = 0.00

            total_261_n_1 = 0.00
            total_261_n_1_6 = 0.00
            erfme = ''
            
            # Tính các tháng n và n-1 được lấy ra từ BAPI trong SAP
            for r in results_mvt_dict[key]:
                budat = datetime.strptime(r["BUDAT"], "%Y%m%d")


                # Tháng n
                # start_date, end_date =  valid.start_end_date(conv_date, 0, 0)
                # if start_date <= budat <= end_date and r['BWART'] in ['261', '262']:
                #     total_261_n += valid.cal_total(r['BWART'],r['MENGE'])
                #     continue

                # Tháng n-1
                start_date, end_date =  valid.start_end_date(conv_date, 1, 1)
                
                if start_date <= budat <= end_date and r['BWART'] in ['309', '310']:
                    # total_309_n_1 += valid.cal_total(r['BWART'],r['MENGE'])
                    # total_309_n_1_3 += valid.cal_total(r['BWART'],r['MENGE'])
                    if ( r['XAUTO'] == 'X' and r['BWART'] == '309' ) or ( r['XAUTO'] == '' and r['BWART'] == '310' ):                 
                        total_309_n_1 += valid.cal_total(r['BWART'],r['MENGE'])
                        total_309_n_1_3 += valid.cal_total(r['BWART'],r['MENGE'])
                    else: 
                        total_309_n_1 -= valid.cal_total(r['BWART'],r['MENGE'])
                        total_309_n_1_3 -= valid.cal_total(r['BWART'],r['MENGE'])

                    continue

                if start_date <= budat <= end_date and r['BWART'] in ['101', '102', '122', '123']:
                    total_101_n_1 += valid.cal_total(r['BWART'],r['MENGE'])
                    total_101_n_1_3 += valid.cal_total(r['BWART'],r['MENGE'])
                    erfme = r['ERFME']
                    continue

                if start_date <= budat <= end_date and r['BWART'] in ['261', '262']:
                    total_261_n_1 += valid.cal_total(r['BWART'],r['MENGE'])
                    total_261_n_1_6 += valid.cal_total(r['BWART'],r['MENGE'])
                    continue


            # Tính tiếp các tháng n-2 đến n-36 được lấy ra từ PostgreSQL cho các giao dịch 309, 310

            for r in mvt_101_dict[key]:

                thang_datetime = datetime.combine(r['thang'], datetime.min.time())  # ✅ chuyển sang datetime

                # Tháng n-1 đến n-3
                start_date, end_date =  valid.start_end_date(conv_date, 1, 3)
                if  start_date <= thang_datetime <= end_date :
                    total_101_n_1_3 += float(r['chenhlech'])
                    erfme = r['erfme']
                    continue
                
                # Tháng n-4 đến n-6
                start_date, end_date =  valid.start_end_date(conv_date, 4, 6)
                if  start_date <= thang_datetime <= end_date :
                    total_101_n_4_6 += float(r['chenhlech'])
                    erfme = r['erfme']
                    continue

                # Tháng n-7 đến n-12
                start_date, end_date =  valid.start_end_date(conv_date, 7, 12)
                if  start_date <= thang_datetime <= end_date :
                    total_101_n_7_12 += float(r['chenhlech'])
                    erfme = r['erfme']
                    continue

                # Tháng n-13 đến n-24
                start_date, end_date =  valid.start_end_date(conv_date, 13, 24)
                if  start_date <= thang_datetime <= end_date :
                    total_101_n_13_24 += float(r['chenhlech'])
                    erfme = r['erfme']
                    continue

                # Tháng n-25 đến n-36
                start_date, end_date =  valid.start_end_date(conv_date, 25, 36)
                if  start_date <= thang_datetime <= end_date :
                    total_101_n_25_36 += float(r['chenhlech'])
                    erfme = r['erfme']
                    continue


            # Tính các tháng n-2 đến n-36 được lấy ra từ PostgreSQL cho các giao dịch 101,102,122,123

            for r in mvt_309_dict[key]:

                thang_datetime = datetime.combine(r['thang'], datetime.min.time())  # ✅ chuyển sang datetime

                # Tháng n-1 đến n-3
                start_date, end_date =  valid.start_end_date(conv_date, 1, 3)
                if  start_date <= thang_datetime <= end_date :
                    total_309_n_1_3 += float(r['chenhlech'])
                    continue
                
                # Tháng n-4 đến n-6
                start_date, end_date =  valid.start_end_date(conv_date, 4, 6)
                if  start_date <= thang_datetime <= end_date :
                    total_309_n_4_6 += float(r['chenhlech'])
                    continue

                # Tháng n-7 đến n-12
                start_date, end_date =  valid.start_end_date(conv_date, 7, 12)
                if  start_date <= thang_datetime <= end_date :
                    total_309_n_7_12 += float(r['chenhlech'])
                    continue

                # Tháng n-13 đến n-24
                start_date, end_date =  valid.start_end_date(conv_date, 13, 24)
                if  start_date <= thang_datetime <= end_date :
                    total_309_n_13_24 += float(r['chenhlech'])
                    continue

                # Tháng n-25 đến n-36
                start_date, end_date =  valid.start_end_date(conv_date, 25, 36)
                if  start_date <= thang_datetime <= end_date :
                    total_309_n_25_36 += float(r['chenhlech'])
                    continue


            # Tính tiếp các tháng n-2 đến n-6 được lấy ra từ PostgreSQL cho các giao dịch 261,262

            for r in mvt_261_dict[key]:

                thang_datetime = datetime.combine(r['thang'], datetime.min.time())  # ✅ chuyển sang datetime

                # Tháng n-1 đến n-6
                start_date, end_date =  valid.start_end_date(conv_date, 1, 6)
                if  start_date <= thang_datetime <= end_date :
                    total_261_n_1_6 += float(r['chenhlech'])
                    continue



            # Tính GR cho tháng n-Future trường hợp user nhập tương lai -> vì chỉ cho tối đa 3 tháng tương lai. Nên chỉ có tháng n-1 đến n-3 bị ảnh hưởng
            total_101_n_1 += valid.sum_cal_next(PO_values,2,month_diff) + valid.sum_cal_next(PR_values,2,month_diff)    
            total_101_n_1_3 += valid.sum_cal_next(PO_values,2,month_diff) + valid.sum_cal_next(PR_values,2,month_diff)
            total_261_n_1_6 += valid.sum_cal_next(RQ_values,2,month_diff)
            
            
            # Với trường hợp đơn vị của GR và đơn vị của Master khác nhau giữa G và KG thì cần convert về đơn vị của Master           
            if erfme.strip() != item["MEINS"].strip() and erfme.strip() in ['G', 'KG'] and item["MEINS"].strip() in ['G', 'KG']:
                total_101_n_1 = valid.convert_unit(total_101_n_1,erfme.strip(),item["MEINS"].strip())
                total_101_n_1_3 = valid.convert_unit(total_101_n_1_3,erfme.strip(),item["MEINS"].strip())
                total_101_n_4_6 = valid.convert_unit(total_101_n_4_6,erfme.strip(),item["MEINS"].strip())
                total_101_n_7_12 = valid.convert_unit(total_101_n_7_12,erfme.strip(),item["MEINS"].strip())
                total_101_n_13_24 = valid.convert_unit(total_101_n_13_24,erfme.strip(),item["MEINS"].strip())
                total_101_n_25_36 = valid.convert_unit(total_101_n_25_36,erfme.strip(),item["MEINS"].strip())

            # Cột AN đến BN
            if total_309_n_1 < 0.00: total_309_n_1 = 0.00
            if total_309_n_1_3 < 0.00: total_309_n_1_3 = 0.00
            if total_309_n_4_6 < 0.00: total_309_n_4_6 = 0.00
            if total_309_n_7_12 < 0.00: total_309_n_7_12 = 0.00
            if total_309_n_13_24 < 0.00: total_309_n_13_24 = 0.00
            if total_309_n_25_36 < 0.00: total_309_n_25_36 = 0.00

            if total < total_309_n_1_3 + total_101_n_1_3:
                AN_Col = total 
            else:
                AN_Col = total_309_n_1_3 + total_101_n_1_3
            AO_Col = AN_Col * NET_PRICE
            AP_Col = AN_Col * STD_PRICE

            if total - AN_Col   < total_309_n_4_6 + total_101_n_4_6:
                AQ_Col = total - AN_Col 
            else:
                AQ_Col = total_309_n_4_6 + total_101_n_4_6
            AR_Col = AQ_Col * NET_PRICE
            AS_Col = AQ_Col * STD_PRICE

            if total_261_n_1_6 < 0:
                AT_Col = 0.00
            else:
                AT_Col = total - AN_Col - AQ_Col

            AU_Col = AT_Col * NET_PRICE
            AV_Col = AT_Col * STD_PRICE

            if total - AN_Col - AQ_Col - AT_Col < total_309_n_7_12 + total_101_n_7_12:
                AW_Col = total - AN_Col - AQ_Col - AT_Col
            else:
                AW_Col = total_309_n_7_12 + total_101_n_7_12

            AX_Col = AW_Col * NET_PRICE
            AY_Col = AW_Col * STD_PRICE

            if total - AN_Col - AQ_Col - AT_Col - AW_Col < total_309_n_13_24 + total_101_n_13_24:
                AZ_Col = total - AN_Col - AQ_Col - AT_Col - AW_Col
            else:
                AZ_Col = total_309_n_13_24 + total_101_n_13_24

            BA_Col = AZ_Col * NET_PRICE
            BB_Col = AZ_Col * STD_PRICE

            if total - AN_Col - AQ_Col - AT_Col - AW_Col - AZ_Col < total_309_n_25_36 + total_101_n_25_36:
                BC_Col = total - AN_Col - AQ_Col - AT_Col - AW_Col - AZ_Col
            else:
                BC_Col = total_309_n_25_36 + total_101_n_25_36

            BD_Col = BC_Col * NET_PRICE
            BE_Col = BC_Col * STD_PRICE


            BF_Col = total - AN_Col - AQ_Col - AT_Col - AW_Col - AZ_Col - BC_Col

            BG_Col = BF_Col * NET_PRICE
            BH_Col = BF_Col * STD_PRICE


            BI_Col = AW_Col + AZ_Col + BC_Col + BF_Col
            BJ_Col = BI_Col * NET_PRICE
            BK_Col = BI_Col * STD_PRICE

            BL_Col = AT_Col + BI_Col
            BM_Col = BL_Col * NET_PRICE
            BN_Col = BL_Col * STD_PRICE

            
            if report_detail != '':
                # Cột BP đến BW


                if MMSTA == 'X1' or ( MMSTA == 'X0' and item["FKGRP"][-2:] == '01' ):
                    BP_Col =  BL_Col
                else:
                    BP_Col =  0.00
                BQ_Col = BP_Col * NET_PRICE

                if item["FKGRP"][-2:] in ['96', 'DE', 'D5', 'DY', '97']:
                    BR_Col =  BL_Col - BP_Col
                else:
                    BR_Col =  0.00
                BS_Col = BR_Col * NET_PRICE

            
                BSTRF_value = float(BSTRF) if BSTRF.strip() else 0.0
                if BL_Col - BP_Col - BR_Col < BSTRF_value:
                # if total <= BSTRF_value:
                    BT_Col = BL_Col - BP_Col - BR_Col
                elif BSTRF_value != 0.0:
                    BT_Col = BSTRF_value - 1
                else:
                    BT_Col = 0.0
                BU_Col = BT_Col * NET_PRICE

                BV_Col = BL_Col - BP_Col - BR_Col - BT_Col
                BW_Col = BV_Col * NET_PRICE


                # Tính cột BY, BZ
                key = (item['MATNR'], item['LIFNR'])                #Tạo Key để tra cứu-> Ko bỏ khoảng trắng
                BY_Col = 0.00
                BZ_Col = 0.00

                for i in ZTMA_MRP1_dict[key]:
                    if i['WERKS'] == item['WERKS']:
                        continue

                    PR_values = [
                    i['MNGPR01'], i['MNGPR02'], i['MNGPR03'], i['MNGPR04'], i['MNGPR05'],
                    i['MNGPR06'], i['MNGPR07'], i['MNGPR08'], i['MNGPR09'], i['MNGPR010'],
                    i['MNGPR011'], i['MNGPR012'], i['MNGPR013'], i['MNGPR014'], i['MNGPR015']
                    ] 

                    BY_Col += valid.sum_cal(PR_values,2,month_diff)


                    RQ_values = [
                    i['MNGRQ01'], i['MNGRQ02'], i['MNGRQ03'], i['MNGRQ04'], i['MNGRQ05'],
                    i['MNGRQ06'], i['MNGRQ07'], i['MNGRQ08'], i['MNGRQ09'], i['MNGRQ010'],
                    i['MNGRQ011'], i['MNGRQ012'], i['MNGRQ013'], i['MNGRQ14'], i['MNGRQ015']
                ]
                    BZ_Col += valid.sum_cal(RQ_values,2,month_diff)




            if report_detail != '':
                result_detail.append({
                        "Plnt": item["WERKS"].strip(),                                                                                                              #1
                        "Material": item["MATNR"].strip(),                                                                                                          #2
                        "Type of material": '',                                                                                                                     #3
                        "Type 2": EXTWG,                                                                                                                            #4
                        "Name": item["MAKTX"].strip(),                                                                                                              #5
                        "Vendor": item["LIFNR"].strip(),                                                                                                            #6
                        "MTyp": item["MTART"].strip(),                                                                                                              #7
                        "PGr": item["FKGRP"].strip(),                                                                                                               #8
                        "MRPC": item["DISPO"].strip(),                                                                                                              #9
                        "Vender Name": NAME1,                                                                                                                       #10
                        "Std Price": STD_PRICE,                                                                                                                     #11
                        "Unit": item["MEINS"].strip(),                                                                                                              #12
                        "Net price": NET_PRICE,                                                                                                                     #13
                        "Unit\u200b": item["BPRME"].strip(),                                                                                                        #14
                        "Currency": item["WAERS"].strip(),                                                                                                          #15
                        "PDT": item["APLFZ"].strip(),                                                                                                               #16
                        "P-S Mat sts": MMSTA,                                                                                                                       #17
                        "MOQ": BSTRF,                                                                                                                               #18
                        "SPQ": BSTMI,                                                                                                                               #19
                        "Sloc": LGFSB,                                                                                                                              #20
                        "Total PO": SUM_PO,                                                                                                                         #21
                        "Total RO": SUM_RO,                                                                                                                         #22
                        "Total PR": SUM_PR,                                                                                                                         #23
                        "Total\n requirement": SUM_RQ,                                                                                                              #24
                        "DISCON": DISCON,                                                                                                                           #25
                        "Qty": total,                                                                                                                               #26
                        "Amt AC": Amt_AC,                                                                                                                           #27
                        "Amt ST": Amt_ST,                                                                                                                           #28
                        "309": total_309_n_1,                                                                                                                       #29
                        "GR": total_101_n_1,                                                                                                                        #30
                        "309\u200b": total_309_n_1_3,                                                                                                               #31
                        "GR\u200b": total_101_n_1_3,                                                                                                                #32
                        "309\u200b\u200b": total_309_n_4_6,                                                                                                         #33
                        "GR\u200b\u200b": total_101_n_4_6,                                                                                                          #34
                        "309\u200b\u200b\u200b": total_309_n_7_12,                                                                                                  #35
                        "GR\u200b\u200b\u200b": total_101_n_7_12,                                                                                                   #36
                        "309\u200b\u200b\u200b\u200b": total_309_n_13_24,                                                                                           #37
                        "GR\u200b\u200b\u200b\u200b": total_101_n_13_24,                                                                                            #38
                        "309\u200b\u200b\u200b\u200b\u200b": total_309_n_25_36,                                                                                     #39
                        "GR\u200b\u200b\u200b\u200b\u200b": total_101_n_25_36,                                                                                      #40
                        "BF result\n tháng N-1": total_261_n_1,                                                                                                     #41
                        "BF result\n tháng N-1 đến N-6": total_261_n_1_6,                                                                                           #42
                        "Qty\u200b": AN_Col,                                                                                                                        #43 Thực tế cột AQ
                        "AC amt\u200b": AO_Col,                                                                                                                     #44 Thực tế cột AR
                        "ST amt\u200b": AP_Col,                                                                                                                     #45 Thực tế cột AS
                        "Qty\u200b\u200b": AQ_Col,                                                                                                                  #46 Thực tế cột AT
                        "AC amt\u200b\u200b": AR_Col,                                                                                                               #47 Thực tế cột AU
                        "ST amt\u200b\u200b": AS_Col,                                                                                                               #48 Thực tế cột AV
                        "Qty\u200b\u200b\u200b": AT_Col,                                                                                                            #49 Thực tế cột AW
                        "AC amt\u200b\u200b\u200b": AU_Col,                                                                                                         #50 Thực tế cột AX
                        "ST amt\u200b\u200b\u200b": AV_Col,                                                                                                         #51 Thực tế cột AY
                        "Qty\u200b\u200b\u200b\u200b": AW_Col,                                                                                                      #52 Thực tế cột AZ
                        "AC amt\u200b\u200b\u200b\u200b": AX_Col,                                                                                                   #53 Thực tế cột BA
                        "ST amt\u200b\u200b\u200b\u200b": AY_Col,                                                                                                   #54 Thực tế cột BB
                        "Qty\u200b\u200b\u200b\u200b\u200b": AZ_Col,                                                                                                #55 Thực tế cột BC
                        "AC amt\u200b\u200b\u200b\u200b\u200b": BA_Col,                                                                                             #56 Thực tế cột BD
                        "ST amt\u200b\u200b\u200b\u200b\u200b": BB_Col,                                                                                             #57 Thực tế cột BE
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b": BC_Col,                                                                                          #58 Thực tế cột BF
                        "AC amt\u200b\u200b\u200b\u200b\u200b\u200b": BD_Col,                                                                                       #59 Thực tế cột BG
                        "ST amt\u200b\u200b\u200b\u200b\u200b\u200b": BE_Col,                                                                                       #60 Thực tế cột BH
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BF_Col,                                                                                    #61 Thực tế cột BI
                        "AC amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BG_Col,                                                                                 #62 Thực tế cột BJ
                        "ST amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BH_Col,                                                                                 #63 Thực tế cột BK
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BI_Col,                                                                              #64 Thực tế cột BL
                        "AC amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BJ_Col,                                                                           #65 Thực tế cột BM
                        "ST amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BK_Col,                                                                           #66 Thực tế cột BN
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BL_Col,                                                                        #67 Thực tế cột BO
                        "AC amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BM_Col,                                                                     #68 Thực tế cột BP
                        "ST amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BN_Col,                                                                     #69 Thực tế cột BQ
                        "PR": BY_Col,                                                                                                                               #70 Thực tế cột BR
                        "Requirement": BZ_Col,                                                                                                                      #71 Thực tế cột BS
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BP_Col,                                                                  #72 Thực tế cột BT
                        "AC Amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BQ_Col,                                                               #73 Thực tế cột BU
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BR_Col,                                                            #74 Thực tế cột BV
                        "AC Amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BS_Col,                                                         #75 Thực tế cột BW
                    })
            if report_summary != '':
                result_summary.append({
                        "Plnt": item["WERKS"].strip(),                                                                                                          #1
                        "Material": item["MATNR"].strip(),                                                                                                      #2
                        "Name": item["MAKTX"].strip(),                                                                                                          #3
                        "Vendor": item["LIFNR"].strip(),                                                                                                        #4
                        "Vender Name": NAME1,                                                                                                                   #5
                        "Std Price": STD_PRICE,                                                                                                                 #6
                        "Unit": item["MEINS"].strip(),                                                                                                          #7
                        "Net price": NET_PRICE,                                                                                                                 #8
                        "Unit\u200b": item["BPRME"].strip(),                                                                                                    #9
                        "Currency": item["WAERS"].strip(),                                                                                                      #10
                        "Qty": total,                                                                                                                           #11
                        "Amt AC": Amt_AC,                                                                                                                       #12
                        "Amt ST": Amt_ST,                                                                                                                       #13
                        "Qty\u200b": AN_Col,                                                                                                                    #14 Thực tế cột N
                        "AC amt\u200b": AO_Col,                                                                                                                 #15 Thực tế cột O
                        "ST amt\u200b": AP_Col,                                                                                                                 #16 Thực tế cột P
                        "Qty\u200b\u200b": AQ_Col,                                                                                                              #17 Thực tế cột Q
                        "AC amt\u200b\u200b": AR_Col,                                                                                                           #18 Thực tế cột R
                        "ST amt\u200b\u200b": AS_Col,                                                                                                           #19 Thực tế cột S
                        "Qty\u200b\u200b\u200b": AT_Col,                                                                                                        #20 Thực tế cột T
                        "AC amt\u200b\u200b\u200b": AU_Col,                                                                                                     #21 Thực tế cột U
                        "ST amt\u200b\u200b\u200b": AV_Col,                                                                                                     #22 Thực tế cột V
                        "Qty\u200b\u200b\u200b\u200b": AW_Col,                                                                                                  #23 Thực tế cột W
                        "AC amt\u200b\u200b\u200b\u200b": AX_Col,                                                                                               #24 Thực tế cột X
                        "ST amt\u200b\u200b\u200b\u200b": AY_Col,                                                                                               #25 Thực tế cột Y
                        "Qty\u200b\u200b\u200b\u200b\u200b": AZ_Col,                                                                                            #26 Thực tế cột Z
                        "AC amt\u200b\u200b\u200b\u200b\u200b": BA_Col,                                                                                         #27 Thực tế cột AA
                        "ST amt\u200b\u200b\u200b\u200b\u200b": BB_Col,                                                                                         #28 Thực tế cột AB
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b": BC_Col,                                                                                      #29 Thực tế cột AC
                        "AC amt\u200b\u200b\u200b\u200b\u200b\u200b": BD_Col,                                                                                   #30 Thực tế cột AD
                        "ST amt\u200b\u200b\u200b\u200b\u200b\u200b": BE_Col,                                                                                   #31 Thực tế cột AE
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BF_Col,                                                                                #32 Thực tế cột AF
                        "AC amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BG_Col,                                                                             #33 Thực tế cột AG
                        "ST amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BH_Col,                                                                             #34 Thực tế cột AH
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BI_Col,                                                                          #35 Thực tế cột AI
                        "AC amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BJ_Col,                                                                       #36 Thực tế cột AJ
                        "ST amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BK_Col,                                                                       #37 Thực tế cột AK
                        "Qty\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BL_Col,                                                                    #38 Thực tế cột AL
                        "AC amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BM_Col,                                                                 #39 Thực tế cột AM
                        "ST amt\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b\u200b": BN_Col,                                                                 #40 Thực tế cột AN
                    })

        print('Dữ liệu của sheet Detail là:',len(result_detail))
        print('Dữ liệu của sheet Summary là:',len(result_summary))

        # Xử lý kết quả
        end = time.time()
        print('Tổng thời gian xử lý:',end - start)

        timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        filename = f"Slow_moving({date})_{timestamp}"
        return excel.export_excel(result_summary, result_detail, filename, down_Radio, serverPath)

    except Exception as e:
        # Trả về lỗi dưới dạng JSON
        print('Lỗi:',e)
        return JsonResponse({
            "Lỗi": str(e),
            "detail": "lỗi"
        }, status=500)
    



@csrf_exempt
@require_http_methods(["POST"])
async def FG_post(request):
    """
    Xử lý POST request từ form
    Đọc dữ liệu SAP và trả về file Excel
    """
    start = time.time()
    # Lấy dữ liệu từ form
    date = request.POST.get('date', '')
    material = request.POST.get('material', '')
    plant = request.POST.getlist('plant')
    down_Radio = request.POST.get('down_Radio', '')
    serverPath = request.POST.get('serverPath', '')

    # Format dữ liệu
    conv_date = valid.format_date(date)
    conv_material = valid.split_and_clean(material)

    try:

        # Build điều kiện WHERE
        builder = condition.WhereConditionBuilder()

        list_material = builder.build_where_conditions(conv_material, column_name="MATNR")

        if plant == ['']:
            list_plant = None
        else:
            list_plant = builder.build_where_conditions(plant, column_name="WERKS")

        list_type = [{'TEXT': "( MTART = 'HALB' OR MTART = 'FERT' )"}]

        # Khởi tạo SAP reader
        reader_instance = get_sap_reader()

        #-------------Get điều kiện cho bảng ZTMA_MTDCSM-------------------------#
        date_month_7 = valid.last_day_previous_month(conv_date,7)[:6]
        last_month_7 = [date_month_7]

        build_condition = builder.build_where_conditions(last_month_7, column_name="SPMON")

        ZTMA_MTDCSM_conditions = builder.merge_multiple_where_conditions(
            [build_condition,list_plant,list_material,list_type]
        )
        print('============================================================')
        print('Lấy dữ liệu bảng: ZTMA_MTDCSM')
        # Lấy dữ liệu của bảng ZTMA_MTDCSM
        ZTMA_MTDCSM_data = sap_reader.SAPTableReader.read_table(reader_instance,'ZTMA_MTDCSM',constants.ZTMA_MTDCSM_FIELDS,ZTMA_MTDCSM_conditions)
    
       # Chuyển dữ liệu đã lấy ở trên thành dạng list
        ZTMA_MTDCSM_list = valid.merge_ZTMA_MTDCSM(ZTMA_MTDCSM_data)

        # Lấy dữ liệu của bảng ZTMA_MTDCSM tháng n-1 để đối chiếu
        date_month_1 = valid.last_day_previous_month(conv_date,1)[:6]
        last_month_1 = [date_month_1]

        build_condition_1 = builder.build_where_conditions(last_month_1, column_name="SPMON")

        ZTMA_MTDCSM_conditions_1 = builder.merge_multiple_where_conditions(
            [build_condition_1,list_plant,list_material,list_type]
        )

        ZTMA_MTDCSM_data_1 = sap_reader.SAPTableReader.read_table(reader_instance,'ZTMA_MTDCSM',constants.ZTMA_MTDCSM_FIELDS,ZTMA_MTDCSM_conditions_1)

        ZTMA_MTDCSM_dict = valid.merge_dict(ZTMA_MTDCSM_data_1)


        # Tạo mảng Material không trùng
        Material_list = sorted(list({item['MATNR'] for item in ZTMA_MTDCSM_list}))

        if list_material == [] or None:
            # conv_material = Material_list
            list_material = builder.build_where_conditions(Material_list, column_name="MATNR")
        

        #-------------Get điều kiện cho bảng MARC-------------------------#
        MARC_conditions = builder.merge_multiple_where_conditions(
            [list_material,list_plant]
        )
        print('Lấy dữ liệu bảng: MARC')
        # Lấy dữ liệu của bảng MARC
        MARC_data = sap_reader.SAPTableReader.read_table(reader_instance,'MARC',constants.MARC_FIELDS,MARC_conditions)


        # Convert data_Marc -> dict, key là tuple (MATNR, WERKS)-> Chú ý: Dữ liệu không được bị trùng
        marc_dict = {(item['MATNR'], item['WERKS']): item for item in MARC_data}

        #-------------Get điều kiện cho các giao dịch MVT-------------------------#
        month_n_1 = valid.last_day_previous_month(conv_date,1)
        new_month_n_1 = [month_n_1][0][:6] + '01'

        end_month_n_1 = [month_n_1][0]
        mvt = ["201", "202", "261", "262","551", "552","553", "554", "555", "556", "557", "558", "559", "560", "601", "602"]

        # Lấy dữ liệu của các MVT tháng n-1 trong SAP
        MVT_data_n_1 = sap_reader.SAPTableReader.get_goods_movement(reader_instance,mvt,Material_list,plant,new_month_n_1,end_month_n_1)


        # Lấy các giao dịch từ tháng n-2 đến n-6 trong PostgreSQL. Chú ý: Các giao dịch này đa xử lý
        end_month_2 = valid.format_date2(valid.last_day_previous_month(conv_date,2))

        new_month_2 = end_month_2[:8] + '01'

        end_month_6 = valid.format_date2(valid.last_day_previous_month(conv_date,6))
        new_month_6 = end_month_6[:8] + '01'


        MVT_data_n_2_6 = await db_postgres.call_single_function(
        'fn_matnr_mvt_201_202_261_262_551_552_553_554_555_556_557_558_559_560_601_602_mv',
        new_month_6,
        new_month_2,
        conv_material,
        plant
        )

        # 1️⃣ Gom nhóm theo key - results_mvt
        mvt_n_1_dict = defaultdict(list)
        for item in MVT_data_n_1:
            key = (item["MATNR"], item["WERKS"])
            mvt_n_1_dict[key].append(item)

        # 1️⃣ Gom nhóm theo key - fn_matnr_mvt_201_202_261_262_551_552_553_554_555_556_557_558_559_560_601_602_mv
        mvt_n_2_6_dict = defaultdict(list)
        for item in MVT_data_n_2_6['data']:
            key = (item["matnr"].strip(), item["werks_d"].strip())
            mvt_n_2_6_dict[key].append(item)

        # Xử lý dữ liệu

        result_data = []             # data
        for item in (i for i in ZTMA_MTDCSM_list if i["Total"] > 0):
            # Tính PRCTR(Cost Center) của MARC
            PRCTR = ''
            key = (item['MATNR'], item['WERKS'])  
            if key in marc_dict:
                marc_item = marc_dict[key]
                PRCTR = marc_item["PRCTR"]

            spmon = f'{item["SPMON"][4:6]}.{item["SPMON"][:4]}'

            key = (item['MATNR'].strip(), item['WERKS'].strip())

            sale_n_6 = 0.00
            sale_n_5 = 0.00
            sale_n_4 = 0.00
            sale_n_3 = 0.00
            sale_n_2 = 0.00
            sale_n_1 = 0.00
            sale_total = 0.00

            # Tính sale các tháng n-2 đến n-6 đã lấy trong PostgreSQL
            for r in mvt_n_2_6_dict[key]:
                thang_datetime = datetime.combine(r['thang'], datetime.min.time())  # ✅ chuyển sang datetime

                #Tháng n-6
                start_date, end_date =  valid.start_end_date(conv_date, 6, 6)

                if  start_date <= thang_datetime <= end_date :
                    sale_n_6 += float(r['chenhlech'])
                    continue
                
                #Tháng n-5
                start_date, end_date =  valid.start_end_date(conv_date, 5, 5)
                if  start_date <= thang_datetime <= end_date :
                    sale_n_5 += float(r['chenhlech'])
                        
                        
                #Tháng n-4
                start_date, end_date =  valid.start_end_date(conv_date, 4, 4)
                if  start_date <= thang_datetime <= end_date :
                    sale_n_4 += float(r['chenhlech'])
                    continue

                #Tháng n-3
                start_date, end_date =  valid.start_end_date(conv_date, 3, 3)
                if  start_date <= thang_datetime <= end_date :
                    sale_n_3 += float(r['chenhlech'])
                    continue

                #Tháng n-2
                start_date, end_date =  valid.start_end_date(conv_date, 2, 2)
                if  start_date <= thang_datetime <= end_date :
                    sale_n_2 += float(r['chenhlech'])
                    continue


            # Tính sale các tháng n-1 lấy trong SAP
            for r in mvt_n_1_dict[key]:      
                budat = datetime.strptime(r["BUDAT"], "%Y%m%d")

                # Tháng n-1
                start_date, end_date =  valid.start_end_date(conv_date, 1, 1)

                if start_date <= budat <= end_date:
                    sale_n_1 += valid.cal_total(r['BWART'],r['MENGE'])
                    continue


            sale_total = sale_n_1 + sale_n_2 + sale_n_3 + sale_n_4 + sale_n_5 + sale_n_6
            slow_qty = float(item["Total"]) - sale_total
            slow_check = ''
            if slow_qty > 0:
                slow_check = 'Slow moving'

            # Tạo key để tìm trong ZTMA_MTDCSM_dict để lấy Inv tháng n-1

            key = (item['MATNR'], item['WERKS'])
            inv_n_1 = 0.00
            for r in ZTMA_MTDCSM_dict[key]: 
                inv_n_1 += r['Total']
                continue

            if slow_qty > inv_n_1:
                final_qty = inv_n_1
            else:
                final_qty = slow_qty


            month_n_1 = valid.last_day_previous_month(conv_date,1)
            month_n_2 = valid.last_day_previous_month(conv_date,2)
            month_n_3 = valid.last_day_previous_month(conv_date,3)
            month_n_4 = valid.last_day_previous_month(conv_date,4)
            month_n_5 = valid.last_day_previous_month(conv_date,5)
            month_n_6 = valid.last_day_previous_month(conv_date,6)

            result_data.append({
                'Plant':                                        item["WERKS"],                          # Cột   1
                "Material":                                     item["MATNR"].strip(),                  #       2
                "Type":                                         item["MTART"].strip(),                  #       3
                "Cost Center":                                  PRCTR.strip(),                          #       4
                "Month":                                        spmon,                                  #       5
                f'Inv {spmon}':                                 item["Total"],                          #       6
                f"Sale {month_n_6[4:6]}.{month_n_6[:4]}":       sale_n_6,                               #       7
                f"Sale {month_n_5[4:6]}.{month_n_5[:4]}":       sale_n_5,                               #       8
                f"Sale {month_n_4[4:6]}.{month_n_4[:4]}":       sale_n_4,                               #       9
                f"Sale {month_n_3[4:6]}.{month_n_3[:4]}":       sale_n_3,                               #       10
                f"Sale {month_n_2[4:6]}.{month_n_2[:4]}":       sale_n_2,                               #       11
                f"Sale {month_n_1[4:6]}.{month_n_1[:4]}":       sale_n_1,                               #       12
                'Sale Total':                                   sale_total,                             #       13
                'Check':                                        slow_check,                             #       14
                'Slow Qty':                                     slow_qty,                               #       15
                f"Inv {month_n_1[4:6]}.{month_n_1[:4]}":        inv_n_1,                                #       16
                'Final slow moving':                            final_qty,                              #       17
            })

        timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        filename = f"Slow_moving(FG-HALB)({date})_{timestamp}"
        # 
        end = time.time()
        print('Tổng thời gian xử lý:',end - start)

        return excel.export_excel_FG(result_data, filename, down_Radio, serverPath)


    except Exception as e:
        # Trả về lỗi dưới dạng JSON
        print('Lỗi:',e)
        return JsonResponse({
            "Lỗi": str(e),
            "detail": "lỗi"
        }, status=500)