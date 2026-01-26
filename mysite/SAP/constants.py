Check_HANA = 'X'                 # Đánh dấu kiểm tra xem đã dùng HANA chưa? Để '' là đang dùng ECC


if Check_HANA == '':                
    # Thông tin kết nối SAP của  ECC
    ASHOST='10.209.11.76'
    CLIENT='300'
    SYSNR='00'
    USER='BGD_MM'
    PASSWD='SapMM123'
    BATCH_SIZE = 15
else:
    # Thông tin kết nối SAP của  HANA
    ASHOST='hana.cmcconsulting.vn'
    CLIENT='120'
    SYSNR='12'
    USER='locnx'
    PASSWD='Lockhongvui98'
    BATCH_SIZE = 15




# SAP Tables Fields
ZTMA_MRP1_FIELDS = [
    'WERKS', 'MATNR', 'MAKTX', 'LIFNR', 'LIFNR_S', 'MTART', 'MEINS', 'FKGRP', 'DISPO', 'STPRS', 'PEINH',
    'NETPR', 'WAERS', 'PEINH_I', 'BPRME', 'APLFZ', 
    'MNG01', 'MNG02', 'MNG03', 'MNG04', 'MNG05', 'MNG06', 'MNG07', 'MNG08', 'MNG09', 'MNG010', 'MNG011', 'MNG012', 'MNG013', 'MNG014', 'MNG015',
    'MNGPR01', 'MNGPR02', 'MNGPR03', 'MNGPR04', 'MNGPR05', 'MNGPR06', 'MNGPR07', 'MNGPR08', 'MNGPR09', 'MNGPR010', 'MNGPR011', 'MNGPR012', 'MNGPR013', 'MNGPR014', 'MNGPR015',
    'MNGRQ01', 'MNGRQ02', 'MNGRQ03', 'MNGRQ04', 'MNGRQ05', 'MNGRQ06', 'MNGRQ07', 'MNGRQ08', 'MNGRQ09', 'MNGRQ010', 'MNGRQ011', 'MNGRQ012', 'MNGRQ013', 'MNGRQ14', 'MNGRQ015',   
]

MARA_FIELDS = ['MATNR', 'EXTWG']

LFA1_FIELDS = ['LIFNR', 'NAME1']

MARC_FIELDS = ['MATNR', 'WERKS','MMSTA', 'DISMM', 'BSTRF', 'BSTMI', 'LGFSB', 'PRCTR', 'BESKZ']

ZTMA_MTDCSM_FIELDS = ['SPMON', 'WERKS', 'LGORT', 'LIFNR', 'MATNR','UMLMD_L', 'LABST_P', 'INSME_P', 'MTART']

T001L_FIELDS = ['WERKS', 'LGORT', 'LGOBE','DISKZ']

TVARVC_FIELDS = ['NAME', 'LOW']