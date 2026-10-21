-- Align persisted position values with the 2027 draft-scoring inputs.
INSERT INTO position_importance (
    position_code, display_name, importance_score, weighting_version, rationale
) VALUES
    ('QB', 'Quarterback', 100, 'baseline-2027-v1', 'Quarterback has the greatest direct influence on offensive operation and team value.'),
    ('WR', 'Wide Receiver', 80, 'baseline-2027-v1', 'Creates separation and explosive receiving value in modern offenses.'),
    ('TE', 'Tight End', 70, 'baseline-2027-v1', 'Provides receiving versatility and formation flexibility.'),
    ('EDGE', 'Edge Rusher', 90, 'baseline-2027-v1', 'Premium pass-rush impact affects pressure, sacks, and defensive disruption.'),
    ('LB', 'Linebacker', 80, 'baseline-2027-v1', 'Contributes to run defense, coverage, and second-level communication.'),
    ('RB', 'Running Back', 70, 'baseline-2027-v1', 'Has offensive value, but replacement and positional volatility reduce baseline priority.'),
    ('OT', 'Offensive Tackle', 90, 'baseline-2027-v1', 'Protects the quarterback and supports efficient offensive execution.'),
    ('IOL', 'Interior Offensive Line', 70, 'baseline-2027-v1', 'Interior protection and blocking support offensive consistency.'),
    ('CB', 'Cornerback', 80, 'baseline-2027-v1', 'Coverage quality limits explosive passing plays and defensive matchup stress.'),
    ('NT', 'Nose Tackle', 60, 'baseline-2027-v1', 'A distinct interior defensive role with a moderate roster-building priority.'),
    ('S', 'Safety', 70, 'baseline-2027-v1', 'Provides coverage range, run support, and pre-snap flexibility.'),
    ('DT', 'Defensive Tackle', 70, 'baseline-2027-v1', 'Interior disruption affects both pass rush and run defense.'),
    ('K', 'Kicker', 30, 'baseline-2027-v1', 'Scoring value matters, but the role has narrower roster impact than core positions.'),
    ('P', 'Punter', 30, 'baseline-2027-v1', 'Special-teams field-position value is important but less central to roster construction.'),
    ('FB', 'Fullback', 30, 'baseline-2027-v1', 'Situational offensive role with limited league-wide usage.'),
    ('LS', 'Long Snapper', 30, 'baseline-2027-v1', 'Specialized role with the narrowest baseline influence on draft value.')
ON CONFLICT (position_code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    importance_score = EXCLUDED.importance_score,
    weighting_version = EXCLUDED.weighting_version,
    rationale = EXCLUDED.rationale;
