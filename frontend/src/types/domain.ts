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
