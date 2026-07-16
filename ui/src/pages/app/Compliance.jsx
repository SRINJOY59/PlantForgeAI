import { ShieldCheck } from "lucide-react";
import Placeholder from "../../components/Placeholder";

export default function Compliance() {
  return (
    <Placeholder icon={ShieldCheck} title="Compliance">
      Overdue inspections and audit-evidence packages, rolled up per unit from
      the compliance scanner. Ask "which inspections are overdue?" meanwhile.
    </Placeholder>
  );
}
