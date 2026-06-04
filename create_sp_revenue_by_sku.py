"""SP_Get_Revenue_By_SKU 생성 스크립트."""
import sys, os
from pathlib import Path
ROOT = Path(r"c:\Dev\SellingFee")
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "db-caller" / "scripts"))
os.chdir(ROOT)
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
import pyodbc, os

driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
server = os.getenv("DB_SERVER", "")
db     = os.getenv("DB_DATABASE", "")
uid    = os.getenv("DB_USER", "")
pwd    = os.getenv("DB_PASSWORD", "")
trust  = os.getenv("DB_TRUST_SERVER_CERT", "no")
cs = (f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};UID={uid};PWD={pwd};TrustServerCertificate={trust};"
      if uid else
      f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};Trusted_Connection=yes;TrustServerCertificate={trust};")

SQL = """
CREATE OR ALTER PROCEDURE dbo.SP_Get_Revenue_By_SKU
    @YYYYMM      CHAR(6),
    @CompanyCode VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @PeriodDate DATE = CONVERT(DATE, @YYYYMM + '01');

    -- OrderMeasure 룰 조회 (고객사별 가산/차감 필드 정의)
    DECLARE
        @s_ItemPrice             CHAR(1),
        @s_ItemTax               CHAR(1),
        @s_ShippingPrice         CHAR(1),
        @s_ShippingTax           CHAR(1),
        @s_GiftWrapPrice         CHAR(1),
        @s_GiftWrapTax           CHAR(1),
        @s_ItemPromotionDiscount CHAR(1),
        @s_ShipPromotionDiscount CHAR(1);

    SELECT
        @s_ItemPrice             = ItemPrice,
        @s_ItemTax               = ItemTax,
        @s_ShippingPrice         = ShippingPrice,
        @s_ShippingTax           = ShippingTax,
        @s_GiftWrapPrice         = GiftWrapPrice,
        @s_GiftWrapTax           = GiftWrapTax,
        @s_ItemPromotionDiscount = ItemPromotionDiscount,
        @s_ShipPromotionDiscount = ShipPromotionDiscount
    FROM dbo.OrderMeasure
    WHERE company_code = @CompanyCode;

    SELECT
        p.name_eng                              AS ProductName,
        ao.SKU,
        SUM(ISNULL(ao.Quantity, 0))             AS QTY,
        ROUND(SUM(
              CASE WHEN @s_ItemPrice = '+'
                   THEN  ISNULL(ao.ItemPrice,             0) * ISNULL(cf.Rate, 0)
                   WHEN @s_ItemPrice = '-'
                   THEN -ISNULL(ao.ItemPrice,             0) * ISNULL(cf.Rate, 0)
                   ELSE 0 END
            + CASE WHEN @s_ItemTax = '+'
                   THEN  ISNULL(ao.ItemTax,               0) * ISNULL(cf.Rate, 0)
                   WHEN @s_ItemTax = '-'
                   THEN -ISNULL(ao.ItemTax,               0) * ISNULL(cf.Rate, 0)
                   ELSE 0 END
            + CASE WHEN @s_ShippingPrice = '+'
                   THEN  ISNULL(ao.ShippingPrice,         0) * ISNULL(cf.Rate, 0)
                   WHEN @s_ShippingPrice = '-'
                   THEN -ISNULL(ao.ShippingPrice,         0) * ISNULL(cf.Rate, 0)
                   ELSE 0 END
            + CASE WHEN @s_ShippingTax = '+'
                   THEN  ISNULL(ao.ShippingTax,           0) * ISNULL(cf.Rate, 0)
                   WHEN @s_ShippingTax = '-'
                   THEN -ISNULL(ao.ShippingTax,           0) * ISNULL(cf.Rate, 0)
                   ELSE 0 END
            + CASE WHEN @s_GiftWrapPrice = '+'
                   THEN  ISNULL(ao.GiftWrapPrice,         0) * ISNULL(cf.Rate, 0)
                   WHEN @s_GiftWrapPrice = '-'
                   THEN -ISNULL(ao.GiftWrapPrice,         0) * ISNULL(cf.Rate, 0)
                   ELSE 0 END
            + CASE WHEN @s_GiftWrapTax = '+'
                   THEN  ISNULL(ao.GiftWrapTax,           0) * ISNULL(cf.Rate, 0)
                   WHEN @s_GiftWrapTax = '-'
                   THEN -ISNULL(ao.GiftWrapTax,           0) * ISNULL(cf.Rate, 0)
                   ELSE 0 END
            + CASE WHEN @s_ItemPromotionDiscount = '+'
                   THEN  ISNULL(ao.ItemPromotionDiscount, 0) * ISNULL(cf.Rate, 0)
                   WHEN @s_ItemPromotionDiscount = '-'
                   THEN -ISNULL(ao.ItemPromotionDiscount, 0) * ISNULL(cf.Rate, 0)
                   ELSE 0 END
            + CASE WHEN @s_ShipPromotionDiscount = '+'
                   THEN  ISNULL(ao.ShipPromotionDiscount, 0) * ISNULL(cf.Rate, 0)
                   WHEN @s_ShipPromotionDiscount = '-'
                   THEN -ISNULL(ao.ShipPromotionDiscount, 0) * ISNULL(cf.Rate, 0)
                   ELSE 0 END
        ), 2)                                   AS RevenueUSD
    FROM dbo.AmzOrder AS ao
    INNER JOIN dbo.Client AS c
        ON ao.Client = c.company_code
    LEFT JOIN dbo.ConvertFx AS cf
        ON  cf.Currency = ISNULL(ao.Currency, 'USD')
        AND cf.Period   = @PeriodDate
    LEFT JOIN dbo.products AS p
        ON p.sku = ao.SKU
    WHERE ao.Period      = @YYYYMM
      AND c.company_code = @CompanyCode
    GROUP BY ao.SKU, p.name_eng
    ORDER BY p.name_eng, ao.SKU;
END;
"""

conn = pyodbc.connect(cs, timeout=30)
try:
    cur = conn.cursor()
    cur.execute(SQL)
    conn.commit()
    print("SP_Get_Revenue_By_SKU 생성 완료")
except Exception as e:
    print(f"ERROR: {e}")
    conn.rollback()
finally:
    conn.close()
