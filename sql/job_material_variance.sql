-- =============================================================================
-- Job Material Variance: standard material cost content vs actual RM issued.
--
--   Standard  = Reporting.vProductStockMovements  (per-unit cost sub-type columns
--               are per FINISHED unit; standard = SUM(rate * units) over 'Received')
--   Actual    = Reporting.vStockMovements         (Despatch - Return, netted)
--   Compared in Rand, grouped by Job + cost sub type.
--
-- The date range selects JOBS by first production receipt; BOTH sides then use the
-- job's FULL totals across all dates (never windowed per row). Windowing either side
-- independently strands the other side's cross-boundary movements and reports huge
-- phantom variances.
-- =============================================================================

DECLARE @DateFrom DATE = '2026-05-01';   -- <<< job production START, inclusive
DECLARE @DateTo   DATE = '2026-07-16';   -- <<< exclusive

-- Jobs whose production STARTED in the window.
WITH JobSet AS (
    SELECT p.fJobNumber
    FROM Reporting.vProductStockMovements AS p
    WHERE p.MovementType = 'Received'
    GROUP BY p.fJobNumber
    HAVING MIN(p.MovementDate) >= @DateFrom
       AND MIN(p.MovementDate) <  @DateTo
),
-- Job header: anchor date = first receipt; units = full production.
Header AS (
    SELECT
        p.fJobNumber                        AS JobNumber,
        MAX(p.JobDesc)                       AS JobDescription,
        MAX(p.Customer_Vendor)              AS CustomerName,
        CAST(MIN(p.MovementDate) AS date)   AS JobDate,
        SUM(p.fUnits)                       AS UnitsProduced
    FROM Reporting.vProductStockMovements AS p
    WHERE p.MovementType = 'Received'
      AND p.fJobNumber IN (SELECT fJobNumber FROM JobSet)
    GROUP BY p.fJobNumber
),
-- Standard: unpivot the per-unit cost-sub-type columns and weight by units.
-- (Add/remove sub types to match your material cost types; labour/overhead
--  columns such as CMT, Overheads, Outwork are intentionally excluded.)
Standard AS (
    SELECT
        p.fJobNumber              AS JobNumber,
        LTRIM(RTRIM(u.Material)) AS Material,
        SUM(u.Rate * p.fUnits)   AS Standard_Cost
    FROM Reporting.vProductStockMovements AS p
    CROSS APPLY (VALUES
        ('Fabric',       p.[Fabric]),
        ('Trims',        p.[Trims]),
        ('Trims Zips',   p.[Trims Zips]),
        ('Trims Tape',   p.[Trims Tape]),
        ('Trims Labels', p.[Trims Labels]),
        ('Trims Cotton', p.[Trims Cotton]),
        ('Trims Packaging', p.[Trims Packaging]),
        ('Trims Elastic',   p.[Trims Elastic]),
        ('Trims Buttons',   p.[Trims Buttons]),
        ('Trims Press Studs', p.[Trims Press Studs]),
        ('Trims Drawcord',  p.[Trims Drawcord]),
        ('Trims Velcro',    p.[Trims Velcro]),
        ('Trims Sticker and Swing Tags', p.[Trims Sticker and Swing Tags]),
        ('Customer Supplied', p.[Customer Supplied])
        -- ... extend with the Fabric <vendor> sub types as needed
    ) AS u(Material, Rate)
    WHERE p.MovementType = 'Received'
      AND p.fJobNumber IN (SELECT fJobNumber FROM JobSet)
    GROUP BY p.fJobNumber, LTRIM(RTRIM(u.Material))
    HAVING SUM(u.Rate * p.fUnits) <> 0
),
-- Actual: net Despatch (stored negative) against Return (stored positive).
Actual AS (
    SELECT
        s.fJobNumber              AS JobNumber,
        LTRIM(RTRIM(s.CostType)) AS Material,
        -SUM(CASE WHEN s.MovementType = 'Despatch' THEN s.MovementValue ELSE 0 END) AS Despatch_Cost,
         SUM(CASE WHEN s.MovementType = 'Return'   THEN s.MovementValue ELSE 0 END) AS Return_Cost,
        -SUM(CASE WHEN s.MovementType IN ('Despatch','Return') THEN s.MovementValue ELSE 0 END) AS Actual_Cost,
        -SUM(CASE WHEN s.MovementType IN ('Despatch','Return') THEN s.fUnits      ELSE 0 END) AS Actual_Units
    FROM Reporting.vStockMovements AS s
    WHERE s.MovementType IN ('Despatch','Return')
      AND s.fJobNumber IN (SELECT fJobNumber FROM JobSet)
    GROUP BY s.fJobNumber, LTRIM(RTRIM(s.CostType))
)
SELECT
    COALESCE(st.JobNumber, ac.JobNumber)  AS JobNumber,
    h.JobDate,
    h.CustomerName,
    h.JobDescription,
    COALESCE(st.Material, ac.Material)     AS Material,
    ISNULL(st.Standard_Cost, 0)            AS Standard_Cost,
    ISNULL(ac.Despatch_Cost, 0)            AS Despatch_Cost,
    ISNULL(ac.Return_Cost, 0)              AS Return_Cost,
    ISNULL(ac.Actual_Cost, 0)              AS Actual_Cost,
    ISNULL(ac.Actual_Units, 0)             AS Actual_Units,
    ISNULL(st.Standard_Cost, 0) - ISNULL(ac.Actual_Cost, 0) AS Variance,
    CASE
        WHEN ISNULL(ac.Actual_Cost,0) > ISNULL(st.Standard_Cost,0) * 1.02 THEN 'Over-issued'
        WHEN ISNULL(ac.Actual_Cost,0) < ISNULL(st.Standard_Cost,0) * 0.98 THEN 'Under-issued'
        ELSE 'On-track'
    END                                    AS VarianceStatus
FROM Standard AS st
FULL OUTER JOIN Actual AS ac
    ON ac.JobNumber = st.JobNumber AND ac.Material = st.Material
LEFT JOIN Header AS h
    ON h.JobNumber = COALESCE(st.JobNumber, ac.JobNumber)
ORDER BY JobNumber, Material;
