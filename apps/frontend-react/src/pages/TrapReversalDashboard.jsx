import FSMCommandCenter from "../components/terminal/FSMCommandCenter";

export default function TrapReversalDashboard(props) {
  return (
    <div className="h-full min-h-0">
      <FSMCommandCenter {...props} className="h-full" />
    </div>
  );
}
