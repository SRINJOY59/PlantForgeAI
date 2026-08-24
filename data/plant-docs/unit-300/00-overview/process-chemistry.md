---
tag: U300-CHEMISTRY
area: Unit 300
equipment_ref: R-101
doc_id: MSC-BBW-U300-CHEMISTRY
revision: A
source: MSC-BBW-U300-MASTER-001
---

# 2. PROCESS DESCRIPTION & REACTION KINETICS

### 2.1 Reactant Feed Specifications
- **Stream A (Hydrogen):** Chain transfer agent controlling polymer melt index.
- **Stream B (Nitrogen):** Inert diluent / blanket gas. Accumulates in recycle loop; purged via HV-901.
- **Stream C (Ethylene):** Primary backbone monomer (C2H4).
- **Stream D (1-Butene):** Comonomer for MSC-6200 (G) grade resin.
- **Stream E (VAM - Vinyl Acetate Monomer):** Comonomer for MSC-8100 (H) grade resin.

### 2.2 Exothermic Kinetics & Thermal Safety
- **Reaction 1 (Forms G Resin):** C + D + A → G (Liquid Resin), ΔH = -95 kJ/mol.
- **Reaction 2 (Forms H Resin):** C + E + A → H (Liquid Resin), ΔH = -108 kJ/mol.
- **Thermal Runaway Risk:** Exothermic reactions exhibit Arrhenius kinetics ($k = A e^{-E_a / RT}$). If reactor temperature exceeds 124.0 °C, reaction rate accelerates nonlinearly, overwhelming jacket cooling capacity ([TV-102](../04-final-control-elements/xmv-10-reactor-cooling-water-valve.md)) and triggering thermal runaway.
- **Safety Interlock:** [SIF-101](../06-safety-instrumented-system/sif-101-reactor-high-temp.md) trips at 128.0 °C, closing all feed valves (FV-101..104) and fully opening cooling water valve TV-102.
