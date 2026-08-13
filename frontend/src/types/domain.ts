/** 도메인 타입 (핸드오프 §20).
 *  수량은 모두 컨테이너 개수(box). TEU 는 별도 필드로만 다룬다. */

export type ContainerSize = '20FT' | '40FT';
export type InventoryMode = 'baseline' | 'postRail';

export interface HubMeta {
  code: string;
  name: string;
  shortName: string;
}

export interface Meta {
  scenario: string;
  horizonStart: string;
  horizonEnd: string;
  horizonDates: string[];
  carrierDataSource: string;
  candidateTimetableSource: string;
  isSyntheticCarrierData: boolean;
  isPrototypeTimetable: boolean;
  allStagesProvenOptimal: boolean;
  carrierKorailViewConsistent: boolean;
  selectedTrainCount: number;
  recommendationCount: number;
  hubs: HubMeta[];
  currentCarrierId: string;
  devMode: boolean;
  availableCarriers: string[];
}

export interface DayAxisEntry {
  date: string;
  weekday: string;
}

export interface DailyInventoryPoint {
  date: string;
  weekday: string;
  closingInventory: number;
  unmetDemand: number;
}

export interface HubWeeklyInventory {
  hubCode: string;
  hubName: string;
  daily: DailyInventoryPoint[];
  weeklyUnmetDemand: number;
}

export interface WeeklyInventoryMatrixData {
  mode: InventoryMode;
  size: ContainerSize;
  days: DayAxisEntry[];
  hubs: HubWeeklyInventory[];
}

export interface WeeklyInventorySummaryData {
  hubCode: string;
  hubName: string;
  size: ContainerSize;
  mode: InventoryMode;
  daily: DailyInventoryPoint[];
  weeklyDemand: number;
  weeklyExternalSupply: number;
  initialInventory: number;
  weekEndInventory: number;
  weeklyInventoryChange: number;
  minimumDisplayedInventory: number;
  weeklyUnmetDemand: number;
  shortageDays: string[];
  railInboundBoxes: number;
  railOutboundBoxes: number;
}

export interface CarrierRecommendation {
  recommendationId: string;
  size: ContainerSize;
  quantityBoxes: number;
  quantityTeu: number;
  originHub: string;
  originName: string;
  destinationHub: string;
  destinationName: string;
  trainId: string;
  departureTime: string;
  arrivalTime: string;
  availableTime: string;
  needCount: number;
  physicalDistanceKm: number;
  participatingCarrierCount: number;
  trainLoadFactor: number;
}

export interface RecommendationStop {
  sequence: number;
  hubCode: string;
  hubName: string;
  arrivalTime: string | null;
  departureTime: string | null;
  availableTime: string | null;
  ownLoadBoxes: Record<ContainerSize, number>;
  ownUnloadBoxes: Record<ContainerSize, number>;
  hasOwnWork: boolean;
}

export interface RecommendationDetail {
  recommendationId: string;
  trainId: string;
  route: string | null;
  candidateSource: string | null;
  stops: RecommendationStop[];
  participatingCarrierCount: number;
  trainLoadFactor: number;
  estimatedRailChargeKrw: number;
  physicalDistanceKm: number;
  tariffDistanceKm: number;
  serviceDueTimeEarliest: string | null;
  serviceDueTimeLatest: string | null;
}

export interface ServiceNeedRow {
  hubCode: string;
  hubName: string;
  size: ContainerSize;
  date: string;
  weekday: string;
  requiredBoxes: number;
  railServedBoxes: number;
  railUnservedBoxes: number;
  needCount: number;
}

export type ImpactRole = '출발' | '도착' | '출발·도착' | '영향 없음';

export interface InventoryImpact {
  hubCode: string;
  hubName: string;
  size: ContainerSize;
  role: ImpactRole;
  inboundBoxes: number;
  outboundBoxes: number;
  baselineMinDisplayedInventory: number;
  postRailMinDisplayedInventory: number;
  baselineStockoutBoxes: number;
  postRailStockoutBoxes: number;
  stockoutReductionBoxes: number;
}

export interface CarrierServiceSummary {
  serviceNeedTeu: number;
  railServedTeu: number;
  railUnservedTeu: number;
  railCoverage: number;
  recommendationCount: number;
  assignedTrainCount: number;
}

export interface OverviewHubSizeState {
  weekEndInventory: number;
  weeklyShortage: number;
  minimumInventory: number;
}

export interface OverviewHub {
  hubCode: string;
  hubName: string;
  shortName: string;
  sizes: Record<ContainerSize, OverviewHubSizeState>;
  hasShortage: boolean;
}

export interface OverviewData {
  carrierId: string;
  hubs: OverviewHub[];
  recommendationPreview: CarrierRecommendation[];
  recommendationTotalCount: number;
  serviceSummary: CarrierServiceSummary | null;
}

export interface OptimizationData {
  carrierId: string;
  needs: ServiceNeedRow[];
  recommendations: CarrierRecommendation[];
  impacts: InventoryImpact[];
  serviceSummary: CarrierServiceSummary | null;
}

/** Rail vs Truck 비교. rail 값은 canonical MILP, truck 값은 비교 입력 데이터. */
export interface TransportRow {
  recommendationId: string;
  trainId: string;
  carrierId: string;
  originHub: string;
  originName: string;
  destinationHub: string;
  destinationName: string;
  size: ContainerSize;
  boxes: number;
  teu: number;
  departureTime: string;
  arrivalTime: string;
  availableTime: string;
  railChargeKrw: number;
  railDistanceKm: number;
  participatingCarrierCount: number;
  trainLoadFactor: number;
  railLoadStartTime: string | null;
  railAvailableTime: string | null;
  railHours: number | null;
  roadDistanceKm: number | null;
  truckVehicles: number | null;
  truckCostKrw: number | null;
  truckHours: number | null;
  truckCo2Kg: number | null;
  railCo2Kg: number | null;
  costSavingKrw: number | null;
  costSavingRate: number | null;
  timeGapHours: number | null;
  carbonSavingKg: number | null;
  carbonSavingRate: number | null;
}

export interface TransportTotals {
  recommendationCount: number;
  boxes: number;
  teu: number;
  boxes20ft: number;
  boxes40ft: number;
  trainIds: string[];
  railChargeKrw: number;
  truckCostKrw: number;
  costSavingKrw: number;
  costSavingRate: number | null;
  avgRailHours: number;
  avgTruckHours: number;
  timeGapHours: number;
  railCo2Kg: number;
  truckCo2Kg: number;
  carbonSavingKg: number;
  carbonSavingRate: number | null;
}

export interface TransportComparison {
  carrierId: string;
  rows: TransportRow[];
  totals: TransportTotals | null;
  missingTruckComparison: string[];
  basis: Record<string, string>;
}

export type TransportPriority = 'cost' | 'time' | 'carbon';

/* ── KORAIL Control Tower ─────────────────────────────────────── */

export interface KorailTrain {
  trainId: string;
  route: string;
  serviceFamily: string | null;
  originTerminal: string | null;
  destinationTerminal: string | null;
  departureTime: string;
  arrivalTime: string;
  formation: string | null;
  wagons: number;
  capacityTeu: number;
  assignedTeu: number;
  loadFactor: number;
  participatingCarrierCount: number;
  boxes20ft: number;
  boxes40ft: number;
  totalBoxes: number;
  candidateSource: string | null;
  trainKm: number;
  workStops: string[];
}

/**
 * stop 에서 상차/하차하는 물량 한 줄 (선사 × 규격 × OD).
 * 상차는 origin == stop.hub, 하차는 destination == stop.hub 인 배정이다.
 */
export interface KorailHandlingItem {
  carrierId: string;
  carrierLabel: string;
  originHub: string;
  originName: string;
  destinationHub: string;
  destinationName: string;
  size: ContainerSize;
  boxes: number;
  teu: number;
}

/**
 * 구간을 통과 중인 물량 한 줄. 구조는 KorailHandlingItem 과 같지만 의미가 다르다.
 * handling 은 그 거점에서 '작업하는' 물량, onboard 는 그 구간에 '실려 있는' 물량이다.
 */
export interface KorailOnboardItem {
  carrierId: string;
  carrierLabel: string;
  originHub: string;
  originName: string;
  destinationHub: string;
  destinationName: string;
  size: ContainerSize;
  boxes: number;
  teu: number;
}

export interface KorailStop {
  sequence: number;
  hubCode: string;
  hubName: string;
  stopType: string | null;
  loadStartTime: string | null;
  arrivalTime: string | null;
  departureTime: string | null;
  availableTime: string | null;
  loadTeu: number;
  unloadTeu: number;
  /** CARRIER_ALLOCATION 에서 직접 집계한 규격별 박스 수 (TEU 역산 아님). */
  loadBoxes20ft: number;
  loadBoxes40ft: number;
  loadBoxesTotal: number;
  unloadBoxes20ft: number;
  unloadBoxes40ft: number;
  unloadBoxesTotal: number;
  /** 합계는 loadBoxesTotal / loadTeu 와 일치한다 (export 시 검증). */
  loadBreakdown: KorailHandlingItem[];
  unloadBreakdown: KorailHandlingItem[];
}

export interface KorailSegment {
  sequence: number;
  fromHub: string;
  fromHubName: string;
  toHub: string;
  toHubName: string;
  loadedTeu: number;
  capacityTeu: number;
  loadFactor: number;
  physicalDistanceKm: number;
  onboardBoxes: number;
  /** loadedTeu 와 일치한다 (export 시 검증). */
  onboardTeu: number;
  onboardCarrierCount: number;
  onboardBreakdown: KorailOnboardItem[];
}

export interface KorailAllocationRow {
  carrierId: string;
  carrierLabel: string;
  originHub: string;
  originName: string;
  destinationHub: string;
  destinationName: string;
  size: ContainerSize;
  boxes: number;
  teu: number;
}

export interface KorailCarrierBreakdown {
  carrierId: string;
  carrierLabel: string;
  boxes: number;
  teu: number;
  boxes20ft: number;
  boxes40ft: number;
  lanes: number;
}

export interface KorailTrainDetail extends KorailTrain {
  stops: KorailStop[];
  segments: KorailSegment[];
  allocation: KorailAllocationRow[];
  carrierBreakdown: KorailCarrierBreakdown[];
}

export interface KorailHubSizeState {
  baselineInventory: number;
  postRailInventory: number;
  demand: number;
  externalSupply: number;
  railInbound: number;
  railOutbound: number;
  baselineStockout: number;
  postRailStockout: number;
}

export interface KorailHubCarrierRow {
  carrierId: string;
  carrierLabel: string;
  sizes: Record<ContainerSize, {
    baselineInventory: number;
    postRailInventory: number;
    baselineStockout: number;
    postRailStockout: number;
    railInbound: number;
    railOutbound: number;
  }>;
}

export interface KorailHub {
  hubCode: string;
  hubName: string;
  shortName: string;
  sizes: Record<ContainerSize, KorailHubSizeState>;
  byCarrier: KorailHubCarrierRow[];
  baselineStockout: number;
  postRailStockout: number;
  stockoutReduction: number;
  status: string;
}

export interface KorailOverview {
  scenario: string;
  serviceNeedTeu: number;
  railServedTeu: number;
  railUnservedTeu: number;
  railCoverage: number;
  selectedTrainCount: number;
  recommendationCount: number;
  boxes20ft: number;
  boxes40ft: number;
  totalBoxes: number;
  trainKm: number;
  wagonKm: number;
  teuKm: number;
  avgLoadFactor: number;
  avgCarriersPerTrain: number;
  estimatedRailChargeKrw: number;
  participatingCarrierCount: number;
  trains: KorailTrain[];
  hubs: KorailHub[];
  needTotals: {
    requiredBoxes: number;
    requiredTeu: number;
    railServedBoxes: number;
    railUnservedBoxes: number;
    needCount: number;
  };
}

export interface KorailNeedRow {
  carrierId: string;
  carrierLabel: string;
  hubCode: string;
  hubName: string;
  size: ContainerSize;
  date: string;
  weekday: string;
  requiredBoxes: number;
  requiredTeu: number;
  railServedBoxes: number;
  railUnservedBoxes: number;
  needCount: number;
  status: string;
}

export interface KorailStationOperation extends KorailStop {
  trainId: string;
}

/** 선정 열차에 배정된 운송 건 하나 (CARRIER_ALLOCATION 1행).
 *  시각은 열차 전체가 아니라 이 건의 origin/destination stop 에서 온 값이다. */
export interface KorailTransportAllocation {
  carrierId: string;
  carrierLabel: string;
  originHub: string;
  originName: string;
  destinationHub: string;
  destinationName: string;
  size: ContainerSize;
  boxes: number;
  teu: number;
  trainId: string;
  originLoadStartTime: string | null;
  originDepartureTime: string | null;
  destinationArrivalTime: string | null;
  destinationAvailableTime: string | null;
}

export interface KorailStationHub {
  hubCode: string;
  hubName: string;
  shortName: string;
  operations: KorailStationOperation[];
  totalLoadTeu: number;
  totalUnloadTeu: number;
  totalLoadBoxes: number;
  totalUnloadBoxes: number;
  totalHandlingTeu: number;
  operationCount: number;
}

export interface KorailInsightItem {
  hubCode: string;
  hubName: string;
  size: ContainerSize;
  baselineStockout: number;
  postRailStockout: number;
  reduction: number;
  railInbound: number;
  railOutbound: number;
  resolved: boolean;
}

export interface KorailInsights {
  stockoutImpacts: KorailInsightItem[];
  totals: { baselineStockout: number; postRailStockout: number; reduction: number };
  lowestLoadSegments: {
    trainId: string;
    fromHubName: string;
    toHubName: string;
    loadedTeu: number;
    capacityTeu: number;
    loadFactor: number;
  }[];
  highestLoadSegments: KorailInsights['lowestLoadSegments'];
}

export interface ChatStatus {
  configured: boolean;
  readOnly: boolean;
  allowedSources: string[];
}

export interface ChatReply {
  reply: string;
  conversationId: string | null;
  sources: string[];
  readOnly: boolean;
}
