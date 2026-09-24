//+------------------------------------------------------------------+
//| Helper: Fetch Entry Price & Entry Time for a Position ID         |
//+------------------------------------------------------------------+
void GetPositionEntryInfo(ulong posId, double &outEntryPrice, long &outEntryTime)
{
   outEntryPrice = 0.0;
   outEntryTime = 0;
   if(posId <= 0) return;

   // Select history deals specifically for this position
   if(HistorySelectByPosition(posId))
   {
      int dealsTotal = HistoryDealsTotal();
      for(int i = 0; i < dealsTotal; i++)
      {
         ulong t = HistoryDealGetTicket(i);
         if(t > 0)
         {
            long entryType = HistoryDealGetInteger(t, DEAL_ENTRY);
            if(entryType == DEAL_ENTRY_IN)
            {
               outEntryPrice = HistoryDealGetDouble(t, DEAL_PRICE);
               outEntryTime = (long)HistoryDealGetInteger(t, DEAL_TIME);
               return; // First DEAL_ENTRY_IN found is the true position open
            }
         }
      }
   }
}
