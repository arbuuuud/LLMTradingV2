//+------------------------------------------------------------------+
//|                                           LLMTradingBridge.mq5   |
//|                          Institutional AI Trading Bridge Client  |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "1.00"
#property strict

//--- Input Parameters
input string   InpServerHost = "127.0.0.1"; // Python Bridge Host
input int      InpServerPort = 5555;        // Python Bridge Port
input string   InpCanonicalSymbol = "XAUUSD"; // Canonical Symbol Name

//--- Global Variables
int      g_socket = INVALID_HANDLE;
datetime g_last_bar_time = 0;
datetime g_last_reconnect_attempt = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   EventSetMillisecondTimer(250); // 250ms polling loop
   ConnectToBridge();
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   CloseBridgeSocket();
}

//+------------------------------------------------------------------+
//| Connect to Python Bridge Server                                  |
//+------------------------------------------------------------------+
bool ConnectToBridge()
{
   if(g_socket != INVALID_HANDLE) return true;

   g_socket = SocketCreate();
   if(g_socket == INVALID_HANDLE)
   {
      Print("Failed to create socket, error: ", GetLastError());
      return false;
   }

   if(!SocketConnect(g_socket, InpServerHost, InpServerPort, 1000))
   {
      CloseBridgeSocket();
      return false;
   }

   Print("Connected to Python Bridge on ", InpServerHost, ":", InpServerPort);
   SendHandshake();
   return true;
}

void CloseBridgeSocket()
{
   if(g_socket != INVALID_HANDLE)
   {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
   }
}

//+------------------------------------------------------------------+
//| Send JSON string to Bridge                                       |
//+------------------------------------------------------------------+
bool SendJSON(string json_str)
{
   if(g_socket == INVALID_HANDLE) return false;

   json_str += "\n";
   uchar data[];
   StringToCharArray(json_str, data, 0, WHOLE_ARRAY, CP_UTF8);
   int len = ArraySize(data) - 1; // remove null terminator

   int sent = SocketSend(g_socket, data, len);
   if(sent < 0)
   {
      Print("SocketSend failed. Closing socket.");
      CloseBridgeSocket();
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Send Broker Specs Handshake                                      |
//+------------------------------------------------------------------+
void SendHandshake()
{
   long acc_num = AccountInfoInteger(ACCOUNT_LOGIN);
   string broker_company = AccountInfoString(ACCOUNT_COMPANY);
   string server_name = AccountInfoString(ACCOUNT_SERVER);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);

   string json = StringFormat(
      "{\"type\":\"HANDSHAKE\",\"symbol\":\"%s\",\"data\":{"
      "\"account_number\":\"%I64d\","
      "\"broker_name\":\"%s\","
      "\"server\":\"%s\","
      "\"balance\":%.2f,"
      "\"equity\":%.2f,"
      "\"broker_symbol\":\"%s\","
      "\"canonical_symbol\":\"%s\","
      "\"digits\":%d,"
      "\"point\":%f,"
      "\"contract_size\":%f,"
      "\"min_lot\":%f,"
      "\"max_lot\":%f,"
      "\"lot_step\":%f,"
      "\"tick_size\":%f,"
      "\"tick_value\":%f}}",
      InpCanonicalSymbol,
      acc_num,
      broker_company,
      server_name,
      balance,
      equity,
      _Symbol,
      InpCanonicalSymbol,
      (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS),
      SymbolInfoDouble(_Symbol, SYMBOL_POINT),
      SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE),
      SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN),
      SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX),
      SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP),
      SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE),
      SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE)
   );
   SendJSON(json);
}

//+------------------------------------------------------------------+
//| Timer function: Reconnect & Incoming Message Processing          |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(g_socket == INVALID_HANDLE)
   {
      datetime now = TimeLocal();
      if(now - g_last_reconnect_attempt >= 5)
      {
         g_last_reconnect_attempt = now;
         ConnectToBridge();
      }
      return;
   }

   // Read socket for incoming commands (BUY, SELL, CLOSE)
   uint readable = SocketIsReadable(g_socket);
   if(readable > 0)
   {
      uchar buffer[];
      int received = SocketRead(g_socket, buffer, readable, 100);
      if(received > 0)
      {
         string msg = CharArrayToString(buffer, 0, received, CP_UTF8);
         // Process incoming commands here
         Print("Command from Python: ", msg);
      }
   }
}

//+------------------------------------------------------------------+
//| OnTick function: Detect New Bar & Send Bar/Tick Events           |
//+------------------------------------------------------------------+
void OnTick()
{
   if(g_socket == INVALID_HANDLE) return;

   datetime current_bar_time = iTime(_Symbol, _Period, 0);

   // Check if a new candle just opened -> previous candle (index 1) closed!
   if(current_bar_time != g_last_bar_time)
   {
      g_last_bar_time = current_bar_time;

      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      if(CopyRates(_Symbol, _Period, 1, 1, rates) == 1)
      {
         MqlDateTime dt;
         TimeToStruct(rates[0].time, dt);
         string time_str = StringFormat("%04d-%02d-%02dT%02d:%02d:%02d",
            dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);

         string bar_json = StringFormat(
            "{\"type\":\"BAR\",\"symbol\":\"%s\",\"data\":{"
            "\"timestamp\":\"%s\","
            "\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,"
            "\"volume\":%d,\"spread\":%d,"
            "\"bid\":%.5f,\"ask\":%.5f}}",
            InpCanonicalSymbol,
            time_str,
            rates[0].open, rates[0].high, rates[0].low, rates[0].close,
            rates[0].tick_volume, rates[0].spread,
            SymbolInfoDouble(_Symbol, SYMBOL_BID),
            SymbolInfoDouble(_Symbol, SYMBOL_ASK)
         );
         SendJSON(bar_json);
      }
   }
}
