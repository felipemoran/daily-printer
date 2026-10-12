import type * as React from 'react';
type Node = React.ReactNode;
export type Tone = 'tone-15' | 'tone-35' | 'tone-50' | 'tone-65';
export type FillPattern = 'solid' | Tone | 'hazard' | 'none';
export type CellState = 'empty' | 'light' | 'tone' | 'solid';

/** print: render exactly the 384-dot raster as <div id="receipt"> (no margins, shadow or desk). */
export interface PaperProps { children?: Node; print?: boolean; feed?: boolean; className?: string }
export interface HeaderBarProps { left: Node; right?: Node; outline?: boolean }
export interface MastheadProps { title: Node; size?: 'xl' | 'lg' | 'md'; aside?: Node | Node[]; sub?: Node; rule?: boolean }
export interface SectionLabelProps { children: Node; style?: React.CSSProperties }
export interface RuleProps { weight?: 'hair' | 'rule' | 'box' | 'heavy' | 'bar' | 'double'; style?: React.CSSProperties }
export interface HazardTapeProps { height?: number }
export interface TearLineProps { label?: string }
export interface FillProps { pattern?: FillPattern; width?: number | string; height?: number; frame?: boolean; children?: Node }
export interface LeadersProps { rows: [Node, Node][] }
export interface CheckboxProps { checked?: boolean }
export interface TaskRowProps { title: Node; meta?: Node; done?: boolean; tag?: Node }
export interface StepProps { n: Node; children: Node; timer?: Node }
export interface LogListProps { rows: [Node, Node][]; timeWidth?: number }
export interface TagProps { children: Node; variant?: 'solid' | 'outline' }
export interface TransitionProps { from: Node; to: Node }
export interface SeverityProps { level: Node; kicker?: Node; lines?: Node[] }
export interface CalloutProps { label: Node; children?: Node; value?: Node }
export interface QuoteProps { children: Node; by?: Node }
export interface StatTile { label?: Node; value: Node; note?: Node; inverted?: boolean }
export interface StatTilesProps { items: StatTile[]; columns?: 1 | 2 | 3; valueFirst?: boolean; small?: boolean; width?: number }
export interface BarRow { label: Node; value: Node; a: number; b?: number; solid?: boolean }
export interface BarListProps { rows: BarRow[]; legend?: [Node, Node?]; marker?: number; tone?: Tone; labelWidth?: number; width?: number }
export interface ColumnsProps { data: { label: Node; value: number; label2?: Node; tone?: Tone }[]; height?: number; width?: number }
export interface CellGridProps {
  rows: { label?: Node; right?: Node; cells: CellState[] | string }[];
  cellWidth?: number; cellHeight?: number; gap?: number; rowGap?: number; ticks?: Node[]; width?: number;
  legend?: [CellState, Node][]; spread?: boolean; labelWidth?: number;
}
export interface DiffGlyphProps { added: number; removed: number }
export interface NoteLinesProps { count?: number }
export interface BoxRowProps { count?: number; filled?: number; columns?: number; width?: number }
/** matrix: QR modules as '1'/'0' strings; module: dots per module; quiet: quiet-zone modules. */
export interface QRSlotProps { matrix?: string[]; module?: number; quiet?: number; src?: string; size?: number; lines?: Node[] }
export interface TextModeProps { lines: (string | { text: string; double?: boolean; reverse?: boolean } | { inverse: string })[] }
export interface ImageProps { src: string; width?: number; height?: number; caption?: Node; alt?: string }

export declare function Paper(p: PaperProps): React.ReactElement;
export declare function HeaderBar(p: HeaderBarProps): React.ReactElement;
export declare function Masthead(p: MastheadProps): React.ReactElement;
export declare function SectionLabel(p: SectionLabelProps): React.ReactElement;
export declare function Rule(p: RuleProps): React.ReactElement;
export declare function HazardTape(p: HazardTapeProps): React.ReactElement;
export declare function TearLine(p: TearLineProps): React.ReactElement;
export declare function Fill(p: FillProps): React.ReactElement;
export declare function Leaders(p: LeadersProps): React.ReactElement;
export declare function Checkbox(p: CheckboxProps): React.ReactElement;
export declare function TaskRow(p: TaskRowProps): React.ReactElement;
export declare function Step(p: StepProps): React.ReactElement;
export declare function LogList(p: LogListProps): React.ReactElement;
export declare function Tag(p: TagProps): React.ReactElement;
export declare function Transition(p: TransitionProps): React.ReactElement;
export declare function Severity(p: SeverityProps): React.ReactElement;
export declare function Callout(p: CalloutProps): React.ReactElement;
export declare function Quote(p: QuoteProps): React.ReactElement;
export declare function StatTiles(p: StatTilesProps): React.ReactElement;
export declare function BarList(p: BarListProps): React.ReactElement;
export declare function Columns(p: ColumnsProps): React.ReactElement;
export declare function CellGrid(p: CellGridProps): React.ReactElement;
export declare function DiffGlyph(p: DiffGlyphProps): React.ReactElement;
export declare function NoteLines(p: NoteLinesProps): React.ReactElement;
export declare function BoxRow(p: BoxRowProps): React.ReactElement;
export declare function QRSlot(p: QRSlotProps): React.ReactElement;
export declare function TextMode(p: TextModeProps): React.ReactElement;
export declare function Image(p: ImageProps): React.ReactElement;
