/** Authority -> the single role permitted to decide it. Mirrors the server; the server decides. */
export const AUTHORITY_ROLE = {
  'QA COI adjudicator': 'identity_adjudicator',
  'Identity adjudicator': 'identity_adjudicator',
  Quality: 'quality_reviewer',
  'Manufacturing planner': 'manufacturing_planner',
  'Logistics coordinator': 'logistics_coordinator',
  Operations: 'ops_coordinator',
};

export function holdsAuthority(authority, roleName) {
  return Boolean(authority) && AUTHORITY_ROLE[authority] === roleName;
}
