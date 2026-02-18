"""EU Small Claims Scoring Pipeline v3.

Three-tier probability model:
  p_recht   (legal merit, after web research)
  p_beweis  (evidence strength, learning from closed cases)
  p_obsiegen = p_recht * p_beweis
  p_eintreibung (recovery, after insolvency + web checks)
  p_gesamt  = p_obsiegen * p_eintreibung
"""
