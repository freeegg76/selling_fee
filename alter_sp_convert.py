"""SP_Convert_Order_Amount_To_USD: ExchangeRate → ConvertFx 로 변경."""
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
if uid and pwd:
    cs = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};UID={uid};PWD={pwd};TrustServerCertificate={trust};"
else:
    cs = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};Trusted_Connection=yes;TrustServerCertificate={trust};"

SQL = """
ALTER PROCEDURE dbo.SP_Convert_Order_Amount_To_USD
    @YYYYMM CHAR(6),
    @CompanyCode VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @PeriodDate DATE;
    SET @PeriodDate = CONVERT(DATE, @YYYYMM + '01');

    SELECT
        ao.Id,
        ao.Period,
        c.company_code,
        c.company_name,
        ao.Client,
        ao.AmazonOrderId,
        ao.MerchantOrderId,
        ao.PurchaseDate,
        ao.OrderStatus,
        ao.FulfillmentChannel,
        ao.SKU,
        ao.ASIN,
        ao.Quantity,
        ao.Currency,
        @PeriodDate          AS RateDate,
        cf.Rate              AS RateToUSD,
        ao.ItemPrice,
        ISNULL(ao.ItemPrice,             0) * ISNULL(cf.Rate, 0) AS ItemPriceUSD,
        ao.ItemTax,
        ISNULL(ao.ItemTax,               0) * ISNULL(cf.Rate, 0) AS ItemTaxUSD,
        ao.ShippingPrice,
        ISNULL(ao.ShippingPrice,         0) * ISNULL(cf.Rate, 0) AS ShippingPriceUSD,
        ao.ShippingTax,
        ISNULL(ao.ShippingTax,           0) * ISNULL(cf.Rate, 0) AS ShippingTaxUSD,
        ao.GiftWrapPrice,
        ISNULL(ao.GiftWrapPrice,         0) * ISNULL(cf.Rate, 0) AS GiftWrapPriceUSD,
        ao.GiftWrapTax,
        ISNULL(ao.GiftWrapTax,           0) * ISNULL(cf.Rate, 0) AS GiftWrapTaxUSD,
        ao.ItemPromotionDiscount,
        ISNULL(ao.ItemPromotionDiscount, 0) * ISNULL(cf.Rate, 0) AS ItemPromotionDiscountUSD,
        ao.ShipPromotionDiscount,
        ISNULL(ao.ShipPromotionDiscount, 0) * ISNULL(cf.Rate, 0) AS ShipPromotionDiscountUSD
    FROM dbo.AmzOrder AS ao
    INNER JOIN dbo.Client AS c
        ON ao.Client = c.company_code
    LEFT JOIN dbo.ConvertFx AS cf
        ON  cf.Currency = ISNULL(ao.Currency, 'USD')
        AND cf.Period   = @PeriodDate
    WHERE ao.Period        = @YYYYMM
      AND c.company_code   = @CompanyCode;
END;
"""

conn = pyodbc.connect(cs, timeout=30)
try:
    cur = conn.cursor()
    cur.execute(SQL)
    conn.commit()
    print("SP_Convert_Order_Amount_To_USD 수정 완료 (ExchangeRate → ConvertFx)")
except Exception as e:
    print(f"ERROR: {e}")
    conn.rollback()
finally:
    conn.close()
