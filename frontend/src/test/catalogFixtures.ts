import type { Finisher, PartSource, ToyCatalog, ToyDetail } from '../api/catalog'

export const finisherA: Finisher = {
  finisher_id: 'FIN-A', finisher_name: 'Alpha Toys', hq_country: 'UK',
}
export const finisherB: Finisher = {
  finisher_id: 'FIN-B', finisher_name: 'Beta Toys', hq_country: 'France',
}
export const uncertainty = 'Actual source unknown. This part has multiple listed suppliers. The supplied data does not identify which source was used for this toy.'

function source(factoryId: string, supplierId: string, isFlagged: boolean): PartSource {
  return {
    unit_cost_usd: '1.25',
    factory: {
      factory_id: factoryId,
      factory_name: `Factory ${factoryId}`,
      address_line: null,
      city: null,
      country: 'India',
    },
    supplier: {
      supplier_id: supplierId,
      supplier_name: `Supplier ${supplierId}`,
      hq_country: 'India',
      is_flagged: isFlagged,
    },
  }
}

export const detailA: ToyDetail = {
  finisher: finisherA,
  toy_id: 'TOY-SHARED',
  toy_name: 'Shared train',
  retail_price_usd: '24.50',
  units_per_year: 1200,
  exposure_status: 'Potentially affected',
  total_parts: 2,
  parts: [
    {
      part_id: 'PART-1', part_name: 'Wheel', quantity: 7,
      distinct_supplier_count: 3, source_uncertainty: uncertainty,
      sources: [source('FAC-1', 'SUP-1', true), source('FAC-2', 'SUP-2', true), source('FAC-3', 'SUP-3', false)],
    },
    {
      part_id: 'PART-2', part_name: 'Axle', quantity: 2,
      distinct_supplier_count: 1, source_uncertainty: null,
      sources: [source('FAC-4', 'SUP-3', false), source('FAC-5', 'SUP-3', false)],
    },
  ],
}

export const detailB: ToyDetail = {
  ...detailA,
  finisher: finisherB,
  retail_price_usd: '31.00',
  units_per_year: 800,
  exposure_status: 'No flagged supplier found',
  parts: detailA.parts.map((part) => ({
    ...part,
    sources: part.sources.map((item) => ({ ...item, supplier: { ...item.supplier, is_flagged: false } })),
  })),
}

export const catalogA: ToyCatalog = {
  finisher: finisherA,
  toys: [detailA, {
    toy_id: 'TOY-OTHER', toy_name: 'Wooden blocks', retail_price_usd: '10.00',
    units_per_year: 500, exposure_status: 'No flagged supplier found',
  }],
  total_toys: 2,
  potentially_affected_toys: 1,
}

export const catalogB: ToyCatalog = {
  finisher: finisherB, toys: [detailB], total_toys: 1, potentially_affected_toys: 0,
}
