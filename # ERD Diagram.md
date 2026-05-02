# ERD Diagram

```mermaid
erDiagram
    Client ||--o{ AmzOrder : "maps by alias"
    Client ||--o{ OrderMeasure : "company_code"
    Client ||--o{ Contract : "company_code"
    Client ||--o{ Fixed : "company_code"
    Client ||--o{ Contact_mail : "company_code"

    Contract ||--o{ Selling_Fee_Rate : "contract_number"
    ExchangeRate ||--o{ AmzOrder : "Currency / RateDate reference"

    Client {
        varchar company_code PK
        nvarchar company_name
        nvarchar address
        varchar business_number
        nvarchar representative
        nvarchar alias
        nvarchar contract_status
    }

    AmzOrder {
        int Id PK
        char Period
        nvarchar Client
        nvarchar AmazonOrderId
        nvarchar MerchantOrderId
        date PurchaseDate
        nvarchar OrderStatus
        nvarchar FulfillmentChannel
        nvarchar SKU
        nvarchar ASIN
        int Quantity
        char Currency
        decimal FXRate
        decimal ItemPrice
        decimal ItemTax
        decimal ShippingPrice
        decimal ShippingTax
        decimal GiftWrapPrice
        decimal GiftWrapTax
        decimal ItemPromotionDiscount
        decimal ShipPromotionDiscount
        nvarchar ShipCity
        nvarchar PromotionIds
        nvarchar PerformanceType
        decimal PerformanceUSD
        datetime CreatedAt
    }

    OrderMeasure {
        varchar company_code PK
        nvarchar company_name
        char ItemPrice
        char ItemTax
        char ShippingPrice
        char ShippingTax
        char GiftWrapPrice
        char GiftWrapTax
        char ItemPromotionDiscount
        char ShipPromotionDiscount
        datetime CreatedAt
        datetime UpdatedAt
    }

    Contract {
        varchar company_code
        nvarchar company_name
        varchar contract_number PK
        date contract_start_date
        date contract_end_date
        int contract_period
        nvarchar contract_status
    }

    Selling_Fee_Rate {
        varchar contract_number FK
        int line_number
        varchar rate_type
        bigint amount_from
        bigint amount_to
        decimal rate
    }

    ExchangeRate {
        int Id PK
        date RateDate
        char Currency
        decimal RateToUSD
        nvarchar Source
        datetime CreatedAt
    }

    Fixed {
        varchar company_code PK
        nvarchar company_name
        varchar service_type
        varchar currency
        decimal base_fee
        decimal extra_brand_fee
        decimal vat
        decimal total_amount
        nvarchar sheet_key
    }

    Contact_mail {
        varchar company_code
        nvarchar company_name
        varchar mail_type
        varchar email
    }