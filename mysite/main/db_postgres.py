# db_postgres.py - Phiên bản STANDALONE (mỗi function có date riêng)

import asyncio
import asyncpg
import time
from datetime import date, datetime
from typing import List, Dict, Any, Optional


# ==================== CẤU HÌNH DATABASE ====================
# THAY ĐỔI CÁC THÔNG TIN NÀY THEO DATABASE CỦA BẠN
DB_CONFIG = {
    'host': 'localhost',           # Địa chỉ PostgreSQL server
    'port': 5432,                  # Port PostgreSQL
    'user': 'postgres',            # Username
    'password': 'admin',   # Password
    'database': 'SCM_control'    # Tên database
}
# ===========================================================


class PostgreSQLAsync:
    """
    Class xử lý truy vấn PostgreSQL bất đồng bộ
    """
    
    def __init__(self, config=None):
        """
        Khởi tạo với config
        
        Args:
            config: Dict config database, nếu None sẽ dùng DB_CONFIG
        """
        self.config = config or DB_CONFIG
    
    async def execute_function(
        self, 
        function_name: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        matnrs: Optional[List[str]] = None,
        plants: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Gọi 1 PostgreSQL function
        
        Args:
            function_name: Tên function (vd: 'fn_matnr_mvt_261_262')
            start_date: Ngày bắt đầu (date object hoặc string 'YYYY-MM-DD')
            end_date: Ngày kết thúc (date object hoặc string 'YYYY-MM-DD')
            matnrs: List material numbers ['MAT001', 'MAT002'] hoặc None (lấy tất cả)
            plants: List plants ['1000', '2000'] hoặc None (lấy tất cả)
        
        Returns:
            {'function_name': str, 'data': list, 'count': int, 'duration': float, 'success': bool, 'error': str}
        """
        print(f"[{time.strftime('%H:%M:%S')}] 🔄 Gọi: {function_name}")
        start_time = time.time()
        
        conn = None
        try:
            conn = await asyncpg.connect(**self.config, timeout=60)
            
            # Convert string to date if needed
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Xử lý NULL cho array parameters
            matnrs_param = matnrs if matnrs and len(matnrs) > 0 else None
            plants_param = plants if plants and len(plants) > 0 else None
            
            # Build query với 4 parameters
            query = f"SELECT * FROM {function_name}($1, $2, $3, $4)"
            
            print(f"   📅 Dates: {start_date} → {end_date} cho {function_name}")
            print(f"   📦 Materials: {matnrs_param if matnrs_param else 'NULL (tất cả)'}")
            print(f"   🏭 Plants: {plants_param if plants_param else 'NULL (tất cả)'}")
            
            # Execute function
            results = await conn.fetch(
                query,
                start_date,      # $1
                end_date,        # $2
                matnrs_param,    # $3 - TEXT[] hoặc NULL
                plants_param     # $4 - TEXT[] hoặc NULL
            )
            
            data = [dict(row) for row in results]
            duration = time.time() - start_time
            
            print(f"[{time.strftime('%H:%M:%S')}] ✅ {function_name}: {len(data)} bản ghi, {duration:.2f}s")
            
            return {
                'function_name': function_name,
                'data': data,
                'count': len(data),
                'duration': duration,
                'success': True,
                'error': None
            }
            
        except Exception as e:
            duration = time.time() - start_time
            print(f"[{time.strftime('%H:%M:%S')}] ❌ {function_name}: {str(e)}")
            
            return {
                'function_name': function_name,
                'data': [],
                'count': 0,
                'duration': duration,
                'success': False,
                'error': str(e)
            }
            
        finally:
            if conn:
                await conn.close()
    
    async def execute_multiple_functions(
        self,
        functions_config: List[Dict[str, Any]],
        matnrs: Optional[List[str]] = None,
        plants: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Gọi nhiều functions song song, MỖI FUNCTION CÓ DATE RIÊNG
        
        Args:
            functions_config: List config cho từng function
                [
                    {
                        'name': 'fn_matnr_mvt_261_262',
                        'start_date': '2024-01-01',
                        'end_date': '2024-12-31'
                    },
                    {
                        'name': 'fn_matnr_mvt_101_102',
                        'start_date': '2024-06-01',  # Khác function 1
                        'end_date': '2024-12-31'
                    }
                ]
            matnrs: List materials (CHUNG cho tất cả functions)
            plants: List plants (CHUNG cho tất cả functions)
        
        Returns:
            List kết quả từ các functions
        """
        print(f"\n{'='*60}")
        print(f"🚀 GỌI {len(functions_config)} FUNCTIONS SONG SONG")
        print(f"   📦 Materials (chung): {matnrs if matnrs else 'NULL (tất cả)'}")
        print(f"   🏭 Plants (chung): {plants if plants else 'NULL (tất cả)'}")
        print(f"{'='*60}\n")
        
        start_time = time.time()
        
        # Tạo tasks cho từng function với date RIÊNG, matnrs/plants CHUNG
        tasks = [
            self.execute_function(
                cfg['name'],
                cfg['start_date'],  # Date riêng cho function này
                cfg['end_date'],    # Date riêng cho function này
                matnrs,             # Materials chung
                plants              # Plants chung
            )
            for cfg in functions_config
        ]
        
        # Chạy song song
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Xử lý exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'function_name': functions_config[i]['name'],
                    'data': [],
                    'count': 0,
                    'duration': 0,
                    'success': False,
                    'error': str(result)
                })
            else:
                processed_results.append(result)
        
        # Tổng hợp
        total_duration = time.time() - start_time
        total_records = sum(r['count'] for r in processed_results if r['success'])
        
        print(f"\n{'='*60}")
        print(f"📊 KẾT QUẢ")
        print(f"{'='*60}")
        print(f"⏱️  Tổng thời gian: {total_duration:.2f}s")
        print(f"📦 Tổng bản ghi: {total_records}")
        
        for r in processed_results:
            status = "✅" if r['success'] else "❌"
            print(f"{status} {r['function_name']}: {r['count']} bản ghi ({r['duration']:.2f}s)")
            if r['error']:
                print(f"   ⚠️  {r['error']}")
        
        print(f"{'='*60}\n")
        
        return processed_results
    
    async def execute_raw_query(self, query: str, params: Optional[List] = None) -> List[Dict[str, Any]]:
        """
        Thực thi raw SQL query
        
        Args:
            query: SQL query
            params: Parameters cho query
        
        Returns:
            List of dicts
        """
        conn = None
        try:
            conn = await asyncpg.connect(**self.config, timeout=60)
            
            if params:
                results = await conn.fetch(query, *params)
            else:
                results = await conn.fetch(query)
            
            return [dict(row) for row in results]
            
        finally:
            if conn:
                await conn.close()


# === WRAPPER FUNCTIONS ĐỂ SỬ DỤNG ===

async def call_material_movement_functions(
    functions_config: List[Dict[str, Any]],
    matnrs: Optional[List[str]] = None,
    plants: Optional[List[str]] = None,
    config: Optional[Dict] = None
):
    """
    Gọi nhiều functions material movement song song
    MỖI FUNCTION CÓ KHOẢNG NGÀY RIÊNG
    
    Args:
        functions_config: Config cho từng function
            [
                {
                    'name': 'fn_matnr_mvt_261_262',
                    'start_date': '2024-01-01',
                    'end_date': '2024-12-31'
                },
                {
                    'name': 'fn_matnr_mvt_101_102_122_123',
                    'start_date': '2024-06-01',  # Khác function trên
                    'end_date': '2024-12-31'
                }
            ]
        matnrs: ['MAT001', 'MAT002'] hoặc None (chung cho tất cả functions)
        plants: ['1000', '2000'] hoặc None (chung cho tất cả functions)
        config: Database config dict (optional)
    
    Usage:
        # Ví dụ 1: 3 functions với date khác nhau
        functions = [
            {
                'name': 'fn_matnr_mvt_261_262',
                'start_date': '2024-01-01',
                'end_date': '2024-12-31'
            },
            {
                'name': 'fn_matnr_mvt_101_102_122_123',
                'start_date': '2024-06-01',  # Chỉ lấy từ tháng 6
                'end_date': '2024-12-31'
            },
            {
                'name': 'fn_matnr_mvt_309_310',
                'start_date': '2024-01-01',
                'end_date': '2024-06-30'     # Chỉ lấy 6 tháng đầu
            }
        ]
        
        results = asyncio.run(call_material_movement_functions(
            functions,
            matnrs=['MAT001', 'MAT002'],  # Chung
            plants=['1000']                # Chung
        ))
        
        # Ví dụ 2: Cùng date range
        functions = [
            {'name': 'fn_matnr_mvt_261_262', 'start_date': '2024-01-01', 'end_date': '2024-12-31'},
            {'name': 'fn_matnr_mvt_101_102_122_123', 'start_date': '2024-01-01', 'end_date': '2024-12-31'},
            {'name': 'fn_matnr_mvt_309_310', 'start_date': '2024-01-01', 'end_date': '2024-12-31'}
        ]
        
        results = asyncio.run(call_material_movement_functions(
            functions,
            None,  # Tất cả materials
            None   # Tất cả plants
        ))
    """
    pg = PostgreSQLAsync(config)
    return await pg.execute_multiple_functions(functions_config, matnrs, plants)


async def call_material_movement_functions_simple(
    start_date: str,
    end_date: str,
    matnrs: Optional[List[str]] = None,
    plants: Optional[List[str]] = None,
    config: Optional[Dict] = None
):
    """
    Helper function: Gọi 3 functions với CÙNG date range
    
    Args:
        start_date: '2024-01-01' (CHUNG cho 3 functions)
        end_date: '2024-12-31' (CHUNG cho 3 functions)
        matnrs: Materials filter (CHUNG)
        plants: Plants filter (CHUNG)
        config: Database config
    
    Usage:
        # Đơn giản: cùng date cho cả 3 functions
        results = asyncio.run(call_material_movement_functions_simple(
            '2024-01-01',
            '2024-12-31',
            ['MAT001'],
            ['1000']
        ))
    """
    functions_config = [
        {
            'name': 'fn_matnr_mvt_261_262',
            'start_date': start_date,
            'end_date': end_date
        },
        {
            'name': 'fn_matnr_mvt_101_102_122_123',
            'start_date': start_date,
            'end_date': end_date
        },
        {
            'name': 'fn_matnr_mvt_309_310',
            'start_date': start_date,
            'end_date': end_date
        }
    ]
    
    pg = PostgreSQLAsync(config)
    return await pg.execute_multiple_functions(functions_config, matnrs, plants)


async def call_single_function(
    function_name: str,
    start_date: str,
    end_date: str,
    matnrs: Optional[List[str]] = None,
    plants: Optional[List[str]] = None,
    config: Optional[Dict] = None
):
    """
    Gọi 1 function cụ thể
    
    Usage:
        result = asyncio.run(call_single_function(
            'fn_matnr_mvt_261_262',
            '2024-01-01',
            '2024-12-31',
            ['MAT001'],
            ['1000']
        ))
    """
    pg = PostgreSQLAsync(config)
    return await pg.execute_function(function_name, start_date, end_date, matnrs, plants)


async def execute_query(query: str, params: Optional[List] = None, config: Optional[Dict] = None):
    """
    Thực thi raw SQL query
    
    Usage:
        query = "SELECT * FROM fn_matnr_mvt_309_310($1, $2, $3, $4)"
        results = asyncio.run(execute_query(
            query, 
            ['2024-01-01', '2024-12-31', None, None]
        ))
    """
    pg = PostgreSQLAsync(config)
    return await pg.execute_raw_query(query, params)


# === PHẦN TEST ===
if __name__ == '__main__':
    """
    Test trực tiếp STANDALONE (không cần Django):
        python db_postgres.py
    
    LƯU Ý: Nhớ sửa DB_CONFIG ở đầu file trước khi chạy!
    """
    
    print("="*70)
    print("🧪 BẮT ĐẦU TEST STANDALONE")
    print("="*70)
    print(f"\n📡 Kết nối đến: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print(f"👤 User: {DB_CONFIG['user']}\n")
    
    # Kiểm tra kết nối
    async def test_connection():
        """Test kết nối database"""
        try:
            conn = await asyncpg.connect(**DB_CONFIG, timeout=10)
            version = await conn.fetchval('SELECT version()')
            await conn.close()
            print(f"✅ Kết nối thành công!")
            print(f"📌 PostgreSQL version: {version[:50]}...\n")
            return True
        except Exception as e:
            print(f"❌ Không thể kết nối database!")
            print(f"⚠️  Lỗi: {e}\n")
            print("💡 Vui lòng kiểm tra DB_CONFIG")
            return False
    
    # Test kết nối trước
    if not asyncio.run(test_connection()):
        print("="*70)
        print("⛔ DỪNG TEST - Không thể kết nối database")
        print("="*70)
        exit(1)
    
    # ========== TEST 1: Mỗi function có date RIÊNG ==========
    print("="*70)
    print("TEST 1: 3 functions với DATE RANGE KHÁC NHAU")
    print("="*70)
    try:
        functions_config = [
            {
                'name': 'fn_matnr_mvt_261_262',
                'start_date': '2024-01-01',
                'end_date': '2024-12-31'     # Cả năm
            },
            {
                'name': 'fn_matnr_mvt_101_102_122_123',
                'start_date': '2024-06-01',
                'end_date': '2024-12-31'     # Chỉ 6 tháng cuối
            },
            {
                'name': 'fn_matnr_mvt_309_310',
                'start_date': '2024-01-01',
                'end_date': '2024-06-30'     # Chỉ 6 tháng đầu
            }
        ]
        
        print("📅 Date ranges:")
        for cfg in functions_config:
            print(f"   {cfg['name']}: {cfg['start_date']} → {cfg['end_date']}")
        print()
        
        results = asyncio.run(call_material_movement_functions(
            functions_config,
            # matnrs=None,  # Tất cả materials
            matnrs=['1AP1024C9XEC4-6C0', '1AP1024CC6TC0-6C0'],  # Tất cả materials
            plants=None   # Tất cả plants
        ))
        
        total = sum(r['count'] for r in results)
        print(f"\n✅ TEST 1 PASSED: Tổng {total} bản ghi")
        
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        print(traceback.format_exc())
    
    # ========== TEST 2: Cùng date, khác materials ==========
    print("\n" + "="*70)
    print("TEST 2: Cùng date range, filter theo materials")
    print("="*70)
    try:
        # Lấy materials mẫu
        async def get_sample_materials():
            pg = PostgreSQLAsync()
            query = "SELECT * FROM fn_matnr_mvt_261_262($1, $2, $3, $4) LIMIT 3"
            try:
                results = await pg.execute_raw_query(
                    query,
                    ['2024-01-01', '2024-01-31', None, None]
                )
                return [r['matnr'] for r in results] if results else None
            except:
                return None
        
        sample_matnrs = asyncio.run(get_sample_materials())
        
        if sample_matnrs:
            print(f"📦 Filter materials: {sample_matnrs}\n")
            
            functions_config = [
                {'name': 'fn_matnr_mvt_261_262', 'start_date': '2024-01-01', 'end_date': '2024-12-31'},
                {'name': 'fn_matnr_mvt_101_102_122_123', 'start_date': '2024-01-01', 'end_date': '2024-12-31'},
                {'name': 'fn_matnr_mvt_309_310', 'start_date': '2024-01-01', 'end_date': '2024-12-31'}
            ]
            
            results = asyncio.run(call_material_movement_functions(
                functions_config,
                matnrs=sample_matnrs,  # Filter materials (chung)
                plants=None            # Tất cả plants
            ))
            
            print(f"\n✅ TEST 2 PASSED: Tổng {sum(r['count'] for r in results)} bản ghi")
        else:
            print("⚠️  Skip test - không lấy được materials mẫu")
            
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
    
    # ========== TEST 3: Dùng helper function (cùng date) ==========
    print("\n" + "="*70)
    print("TEST 3: Dùng helper function - CÙNG date cho cả 3 functions")
    print("="*70)
    try:
        results = asyncio.run(call_material_movement_functions_simple(
            '2024-01-01',
            '2024-01-31',
            matnrs=None,
            plants=None
        ))
        
        print(f"\n✅ TEST 3 PASSED: Tổng {sum(r['count'] for r in results)} bản ghi")
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
    
    # ========== TEST 4: Gọi 1 function riêng ==========
    print("\n" + "="*70)
    print("TEST 4: Gọi 1 function riêng")
    print("="*70)
    try:
        result = asyncio.run(call_single_function(
            'fn_matnr_mvt_309_310',
            '2024-01-01',
            '2024-12-31',
            None,
            None
        ))
        print(f"\n✅ TEST 4 PASSED: {result['count']} bản ghi")
        
    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
    
    # ========== TEST 5: Date ranges phức tạp ==========
    print("\n" + "="*70)
    print("TEST 5: Date ranges phức tạp - mỗi function khác nhau hoàn toàn")
    print("="*70)
    try:
        functions_config = [
            {
                'name': 'fn_matnr_mvt_261_262',
                'start_date': '2024-01-01',
                'end_date': '2024-03-31'     # Q1
            },
            {
                'name': 'fn_matnr_mvt_101_102_122_123',
                'start_date': '2024-04-01',
                'end_date': '2024-06-30'     # Q2
            },
            {
                'name': 'fn_matnr_mvt_309_310',
                'start_date': '2024-07-01',
                'end_date': '2024-09-30'     # Q3
            }
        ]
        
        print("📅 Date ranges (theo quý):")
        for cfg in functions_config:
            print(f"   {cfg['name']}: {cfg['start_date']} → {cfg['end_date']}")
        print()
        
        results = asyncio.run(call_material_movement_functions(
            functions_config,
            matnrs=None,
            plants=None
        ))
        
        print(f"\n✅ TEST 5 PASSED: Tổng {sum(r['count'] for r in results)} bản ghi")
        
    except Exception as e:
        print(f"\n❌ TEST 5 FAILED: {e}")
    
    # ========== KẾT THÚC ==========
    print("\n" + "="*70)
    print("🎉 HOÀN THÀNH TẤT CẢ TEST")
    print("="*70)
    print("\n💡 CÁCH SỬ DỤNG:")
    print("""
    # 1. Mỗi function có date RIÊNG (linh hoạt)
    functions = [
        {'name': 'fn_matnr_mvt_261_262', 'start_date': '2024-01-01', 'end_date': '2024-12-31'},
        {'name': 'fn_matnr_mvt_101_102_122_123', 'start_date': '2024-06-01', 'end_date': '2024-12-31'},
        {'name': 'fn_matnr_mvt_309_310', 'start_date': '2024-01-01', 'end_date': '2024-06-30'}
    ]
    results = asyncio.run(call_material_movement_functions(
        functions,
        matnrs=['MAT001'],  # Chung
        plants=['1000']     # Chung
    ))
    
    # 2. Cùng date cho cả 3 functions (đơn giản)
    results = asyncio.run(call_material_movement_functions_simple(
        '2024-01-01',
        '2024-12-31',
        matnrs=None,
        plants=None
    ))
    
    # 3. Gọi 1 function
    result = asyncio.run(call_single_function(
        'fn_matnr_mvt_261_262',
        '2024-01-01',
        '2024-12-31'
    ))
    """)