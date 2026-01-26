import copy

class WhereConditionBuilder:
    def __init__(self, field_name="TEXT"):
        """
        field_name : key trong dictionary (mặc định 'TEXT')
        """
        self.field_name = field_name

    def build_where_conditions(self, list_condition, column_name="MATNR"):
        """
        Tạo list dictionary cho điều kiện WHERE theo dạng:
        [{'TEXT': "( MATNR = '...' "}, {'TEXT': " OR MATNR = '...' )"}]

        list_condition : list giá trị cần lọc (VD: mã vật tư, Plant...)
        column_name    : tên cột để so sánh (mặc định 'MATNR')
        """
        field_list = []

        for stt, condition in enumerate(list_condition, start=1):
            if stt == 1:
                if stt == len(list_condition):
                    # Chỉ có 1 phần tử
                    field_list.append({self.field_name: f"( {column_name} = '{condition}' )"})
                else:
                    # Phần tử đầu tiên
                    field_list.append({self.field_name: f"( {column_name} = '{condition}' "})
            elif stt == len(list_condition):
                # Phần tử cuối
                field_list.append({self.field_name: f" OR {column_name} = '{condition}' )"})
            else:
                # Phần tử ở giữa
                field_list.append({self.field_name: f" OR {column_name} = '{condition}' "})
        return field_list

    def merge_multiple_where_conditions(self, lists_of_conditions):
        merged = []
        has_data_before = False

        for cond_list in lists_of_conditions:
            if not cond_list:
                continue  # bỏ qua list trống

            # deep copy để không ảnh hưởng dữ liệu gốc
            cond_list = copy.deepcopy(cond_list)

            if has_data_before:
                cond_list[0][self.field_name] = ' and ' + cond_list[0][self.field_name]

            merged.extend(cond_list)
            has_data_before = True

        return merged


# =============================
# Ví dụ sử dụng
# =============================

# builder = WhereConditionBuilder()

# materials = ['PGHR1272ZA/C9', 'PNHP1069ZA/V1', 'D0GA223JA070']
# field_list1 = builder.build_where_conditions(materials, column_name="MATNR")

# plants = ['VB01', 'VE01', 'VG01']
# field_list2 = builder.build_where_conditions(plants, column_name="WERKS")

# others = ['A1', 'B2']
# field_list3 = builder.build_where_conditions(others, column_name="SOME_FIELD")

# all_conditions = builder.merge_multiple_where_conditions([field_list1, field_list2, field_list3])

# print(all_conditions)
# print(field_list1)
# print(field_list2)
# print(field_list3)
