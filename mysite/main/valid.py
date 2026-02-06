from datetime import datetime, timedelta
from collections import defaultdict
from django.utils import timezone


def split_and_clean(input_string: str) -> list:
    # Tách chuỗi dựa trên \r\n
    result = input_string.split('\r\n')
    # Loại bỏ dấu cách và các ký tự trắng, bỏ các chuỗi rỗng
    result = [item.replace(" ", "").strip() for item in result if item.strip()]
    return result


def format_date(input_date: str) -> str:
    # Chuyển chuỗi thành đối tượng datetime
    date_obj = datetime.strptime(input_date, "%Y-%m-%d")
    # Định dạng lại thành YYYYMMDD
    return date_obj.strftime("%Y%m%d")


def format_date2(date_str: str) -> str:
    """
    Chuyển chuỗi ngày dạng YYYYMMDD thành YYYY-MM-DD.
    
    Ví dụ:
        format_date("20240101") -> "2024-01-01"
    """
    # Kiểm tra độ dài hợp lệ
    if len(date_str) != 8 or not date_str.isdigit():
        raise ValueError("Ngày không hợp lệ. Vui lòng nhập dạng 'YYYYMMDD'.")
    
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"


def last_day_previous_month(date_input, months_before=1):
    """
    Trả về ngày cuối cùng của N tháng trước từ một ngày cho trước.
    - date_input: dạng datetime hoặc chuỗi 'YYYYMMDD'
    - months_before: số tháng lùi về trước (mặc định 1)
    - Kết quả trả về: chuỗi 'YYYYMMDD'
    """
    if isinstance(date_input, str):
        date_input = datetime.strptime(date_input, "%Y%m%d")

    # Xác định tháng và năm của tháng cần tìm
    month = date_input.month - months_before
    year = date_input.year

    # Nếu month <= 0 thì lùi về năm trước
    while month <= 0:
        month += 12
        year -= 1

    # Lấy ngày đầu của tháng cần tìm, rồi cộng thêm 1 tháng và trừ 1 ngày
    first_day_target_month = datetime(year, month, 1)
    first_day_next_month = (first_day_target_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    last_day_target_month = first_day_next_month - timedelta(days=1)

    return last_day_target_month.strftime("%Y%m%d")

# # ================== Ví dụ sử dụng ==================
# print(last_day_previous_month("20250815"))  # 2025-07-31
# print(last_day_previous_month(datetime(2025, 1, 10)))  # 2024-12-31

def calculate_std_price(element1, element2, decimal_places):
    """
    Tính STD_PRICE từ hai phần tử và làm tròn theo số chữ số thập phân chỉ định.
    
    Args:
        element1 (str): Giá trị STPRS (dạng chuỗi).
        element2 (str): Giá trị PEINH (dạng chuỗi).
        decimal_places (int): Số chữ số thập phân mong muốn cho kết quả.
        
    Returns:
        dict: Dictionary với key 'STD_PRICE' chứa giá trị đã tính hoặc 0 nếu có lỗi.
    """
    try:
        stprs = float(element1)  # Chuyển phần tử 1 sang float
        peinh = float(element2)  # Chuyển phần tử 2 sang float
        std_price = round(stprs / peinh, decimal_places) if peinh != 0 else 0  # Làm tròn theo số thập phân
        return std_price
    except (ValueError, TypeError):
        return 0  # Xử lý lỗi giá trị không hợp lệ
    except ZeroDivisionError:
        return 0  # Xử lý lỗi chia cho 0
    


def convert_to_float(value):
    """
    Chuyển chuỗi chứa số với dấu trừ ở cuối thành số float.
    
    Args:
        value (str): Chuỗi cần chuyển, ví dụ: '         901.000-'.
        
    Returns:
        float: Giá trị số, hoặc 0.0 nếu không thể chuyển đổi.
    """
    try:
        # Loại bỏ khoảng trắng
        cleaned_value = value.strip()
        # Kiểm tra nếu chuỗi kết thúc bằng dấu trừ
        if cleaned_value.endswith('-'):
            # Di chuyển dấu trừ về đầu chuỗi
            cleaned_value = '-' + cleaned_value.rstrip('-')
        # Chuyển thành float
        return float(cleaned_value)
    except (ValueError, TypeError):
        return 0.0  # Trả về 0.0 nếu không thể chuyển đổi
    
def sum_cal(values, rounds=2, next=0):
    """
    Tính tổng 12 phần tử liên tiếp trong danh sách 'values',
    bắt đầu từ phần tử có index = next.
    Ví dụ:
      next = 0 -> MNG01..MNG012
      next = 2 -> MNG03..MNG014
    """
    # Lấy 12 phần tử từ vị trí next
    subset = values[next:next+12]

    SUM = 0.0
    for value in subset:
        try:
            cleaned_value = str(value).strip()
            # xử lý trường hợp '123-' -> '-123'
            if cleaned_value.endswith('-'):
                cleaned_value = '-' + cleaned_value.rstrip('-').strip()
            # loại bỏ dấu phẩy ngăn cách hàng nghìn
            cleaned_value = cleaned_value.replace(',', '')
            SUM += float(cleaned_value)
        except (ValueError, TypeError):
            continue

    return round(SUM, rounds)



def sum_cal_next(values, rounds=2, next=0):
    """
    Tính tổng các phần tử trong danh sách 'values'
    từ MNG01 đến MNG0<next>.
    
    Quy tắc:
      next = 0 -> không tính (trả về 0)
      next = 2 -> tính MNG01..MNG02
      next = 3 -> tính MNG01..MNG03
    """
    # Nếu next = 0 hoặc âm thì không tính
    if next <= 0:
        return 0.0

    # Lấy phần tử từ đầu đến index (next-1)
    subset = values[:next]

    SUM = 0.0
    for value in subset:
        try:
            cleaned_value = str(value).strip()
            # xử lý trường hợp '123-' -> '-123'
            if cleaned_value.endswith('-'):
                cleaned_value = '-' + cleaned_value.rstrip('-').strip()
            # loại bỏ dấu phẩy ngăn cách hàng nghìn
            cleaned_value = cleaned_value.replace(',', '')
            SUM += float(cleaned_value)
        except (ValueError, TypeError):
            continue

    return round(SUM, rounds)




def check_discon(value):
    # Lấy giá trị  và làm sạch
    cleaned_value = value.strip()
    # Lấy 2 ký tự từ bên phải
    right_two_chars = cleaned_value[-2:]

    # Kiểm tra xem ở điểu kiện nào
    if right_two_chars in ['96', 'DE', 'D5', 'DY']:
        rs = '1. Discont'
    elif right_two_chars in ['97']:
        rs = '2. Future Discont'
    else:
        rs = '3. No Discont'
    
    return rs


def cal_total(BWART, value):

    if BWART in ['101', '123', '202', '262', '551', '553', '555', '557', '559', '602']:
        rs = float(value)
    elif BWART in ['102', '122', '201', '261', '552', '554', '556', '558', '560', '601']:
        rs = - float(value)
    else:
        rs = float(value)

    return rs

def start_end_date(date, start, end):
    last_n_1 = last_day_previous_month(date,start)
    last_n_2 = last_day_previous_month(date,end)
    begin_n_2= last_n_2[:6] + '01'
    start_date = datetime.strptime(begin_n_2, "%Y%m%d")
    end_date = datetime.strptime(last_n_1, "%Y%m%d")
    return start_date, end_date


def month_diff(input_date_str):
    """
    Tính số tháng chênh lệch giữa ngày nhập vào và ngày hiện tại.
    Trả về số nguyên (âm nếu ngày nhập nhỏ hơn hiện tại).
    Ví dụ:
        - Hôm nay: 2025-10-30
        - input_date_str = '2025-11-01' -> kết quả = 1
    """
    # Chuyển chuỗi thành datetime
    input_date = datetime.strptime(input_date_str, "%Y-%m-%d")
    today = timezone.localdate()

    # Tính chênh lệch theo tháng
    diff = (input_date.year - today.year) * 12 + (input_date.month - today.month)

    return diff



def split_date_range(start_date: str, end_date: str = '', step_days: int = 3):
    """
    Chia khoảng thời gian thành các nhóm (start, end) theo step_days.
    - start_date: ngày bắt đầu (YYYY-MM-DD)
    - end_date: ngày kết thúc (YYYY-MM-DD), có thể để trống
    - step_days: số ngày mỗi nhóm (mặc định = 3)
    
    Trả về danh sách tuple dạng chuỗi: [('2025-10-01','2025-10-03'), ...]
    """
    
    # Nếu start_date hoặc end_date là datetime → chuyển sang string
    if isinstance(start_date, datetime):
        start_date = start_date.strftime("%Y-%m-%d")
    if isinstance(end_date, datetime):
        end_date = end_date.strftime("%Y-%m-%d")


    # Nếu không có end_date → chỉ trả về 1 ngày
    if not end_date or end_date.strip() == "":
        return [(start_date, start_date)]

    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    result = []
    current = start

    while current <= end:
        next_date = current + timedelta(days=step_days - 1)
        if next_date < end:
            result.append((
                current.strftime("%Y-%m-%d"),
                next_date.strftime("%Y-%m-%d")
            ))
        else:
            result.append((
                current.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d")
            ))
            break
        current = next_date + timedelta(days=1)

    return result


def merge_ZTMA_MTDCSM(ZTMA_MTDCSM_data):
    """
    Gộp tồn kho theo key (MATNR, WERKS)
    - Cộng dồn UMLMD_L, LABST_P, INSME_P, Total
    - Lấy SPMON, MTART theo dòng đầu tiên của mỗi nhóm

    Args:
        ZTMA_MTDCSM_data (list[dict]): danh sách dữ liệu từ ZTMA_MTDCSM

    Returns:
        list[dict]: danh sách đã gộp
    """
    merged = {}

    for row in ZTMA_MTDCSM_data:
        key = (row['MATNR'], row['WERKS'])

        # Convert giá trị về float
        uml = float(row['UMLMD_L'])
        lab = float(row['LABST_P'])
        ins = float(row['INSME_P'])
        total = uml + lab + ins

        if key not in merged:
            merged[key] = {
                'SPMON': row['SPMON'],
                'MATNR': row['MATNR'],
                'WERKS': row['WERKS'],
                'MTART': row['MTART'],
                'UMLMD_L': uml,
                'LABST_P': lab,
                'INSME_P': ins,
                'Total': total
            }
        else:
            merged[key]['UMLMD_L'] += uml
            merged[key]['LABST_P'] += lab
            merged[key]['INSME_P'] += ins
            merged[key]['Total'] += total

    return list(merged.values())



def merge_dict(data):
    """
    Trả về dict:
        key = (MATNR, WERKS)
        value = list các dòng (SPMON, UMLMD_L, LABST_P, INSME_P, Total)
    """
    result = defaultdict(list)

    for row in data:
        key = (row['MATNR'], row['WERKS'])

        uml = float(row['UMLMD_L'])
        lab = float(row['LABST_P'])
        ins = float(row['INSME_P'])
        total = uml + lab + ins

        result[key].append({
            'SPMON': row['SPMON'],
            'MATNR': row['MATNR'],
            'WERKS': row['WERKS'],
            'MTART': row['MTART'],
            'UMLMD_L': uml,
            'LABST_P': lab,
            'INSME_P': ins,
            'Total': total
        })

    return result


def convert_unit(value, from_unit, to_unit):
    # chuẩn hóa đơn vị về chữ hoa
    from_unit = from_unit.upper()
    to_unit = to_unit.upper()

    # bảng quy đổi về đơn vị chuẩn GRAM
    factors = {
        "MG": 0.001,
        "G": 1,
        "KG": 1000,
        "TON": 1_000_000,
    }

    # kiểm tra đơn vị hợp lệ
    if from_unit not in factors or to_unit not in factors:
        raise ValueError("Đơn vị không hợp lệ. Hỗ trợ: MG, G, KG, TON")

    # đổi giá trị về GRAM trước
    value_in_g = value * factors[from_unit]

    # đổi từ GRAM sang đơn vị đích
    result = value_in_g / factors[to_unit]

    return result



def build_inventory_conditions_split():
    fields = [
        "INVENTORY",
        "LABST",

        "MNG01", "MNGPR01", "MNGRQ01", "MNGPL01", "MNGRO01",
        "MNG02", "MNGPR02", "MNGRQ02", "MNGPL02", "MNGRO02",
        "MNG03", "MNGPR03", "MNGRQ03", "MNGPL03", "MNGRO03",
        "MNG04", "MNGPR04", "MNGRQ04", "MNGPL04", "MNGRO04",
        "MNG05", "MNGPR05", "MNGRQ05", "MNGPL05", "MNGRO05",
        "MNG06", "MNGPR06", "MNGRQ06", "MNGPL06", "MNGRO06",
        "MNG07", "MNGPR07", "MNGRQ07", "MNGPL07", "MNGRO07",
        "MNG08", "MNGPR08", "MNGRQ08", "MNGPL08", "MNGRO08",
        "MNG09", "MNGPR09", "MNGRQ09", "MNGPL09", "MNGRO09",

        "MNG010", "MNGPR010", "MNGRQ010", "MNGPL010", "MNGRO010",
        "MNG011", "MNGPR011", "MNGRQ011", "MNGPL011", "MNGRO011",
        "MNG012", "MNGPR012", "MNGRQ012", "MNGPL012", "MNGRO012",
        "MNG013", "MNGPR013", "MNGRQ013", "MNGPL013", "MNGRO013",
        "MNG014", "MNGPR014", "MNGRQ14",  "MNGPL014", "MNGRO014",
        "MNG015", "MNGPR015", "MNGRQ015", "MNGPL015", "MNGRO015",

        "VMLAB",
        "SLABS",
        "SPEME",
        "VMSPE",
        "EISBE",
    ]

    result = []
    for i, f in enumerate(fields):
        if i == 0:
            result.append({"TEXT": f"( {f} <> 0"})
        elif i == len(fields) - 1:
            result.append({"TEXT": f" OR {f} <> 0 )"})
        else:
            result.append({"TEXT": f" OR {f} <> 0"})
    return result
