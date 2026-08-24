import { Navigate, useParams } from 'react-router-dom';

export function PurchaseDetailPage() {
  const { purchaseId = '' } = useParams();

  if (!purchaseId) {
    return <Navigate to="/purchases" replace />;
  }

  return (
    <Navigate
      to={`/purchases?purchaseId=${encodeURIComponent(purchaseId)}`}
      replace
    />
  );
}
