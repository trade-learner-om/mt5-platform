import AddIndianAccountModal from "./indian/AddIndianAccountModal";
import AddInternationalAccountModal from "./international/AddInternationalAccountModal";

export default function AddAccountModal({ open, onClose, onSubmit, initialMarket = "INTERNATIONAL", token }) {
  const normalizedMarket = String(initialMarket || "INTERNATIONAL").toUpperCase() === "INDIAN" ? "INDIAN" : "INTERNATIONAL";
  if (normalizedMarket === "INDIAN") {
    return <AddIndianAccountModal open={open} onClose={onClose} onSubmit={onSubmit} />;
  }
  return <AddInternationalAccountModal open={open} token={token} onClose={onClose} onSubmit={onSubmit} />;
}
