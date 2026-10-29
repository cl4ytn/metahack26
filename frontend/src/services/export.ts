import type { ArchitectureGraph } from '../types/graph'
/** JSON is a YAML 1.2 subset; preserves the entire graph without ad-hoc escaping. */
export function serializeGraph(graph: ArchitectureGraph): string {return JSON.stringify(graph, null, 2) + '\n'}
