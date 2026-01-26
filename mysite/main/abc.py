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


PO_values = [
                1, 2, 3, 4, 5,
                6, 7, 8, 9, 10,
                11, 12, 13, 14, 15
            ]


# next = 0 -> tính MNG01..MNG012
SUM_all = sum_cal(PO_values, 2, 1)
print(SUM_all)


from datetime import datetime

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
    today = datetime.today()

    # Tính chênh lệch theo tháng
    diff = (input_date.year - today.year) * 12 + (input_date.month - today.month)

    return diff


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


sum_next = sum_cal_next(PO_values,2,-1)
print(sum_next)