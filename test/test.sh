#!/bin/bash
#
# Test Script for Powerwall Simulator
#

# Valid Login Request
echo "------------------------------------------------"
echo "Trying valid request for login: "
echo "------------------------------------------------"
curl 'https://localhost/api/login/Basic' \
  --data-raw $'{"username":"customer","password":"password","email":"test@example.com","clientInfo":{"timezone":"America/Los_Angeles"}}' \
  --compressed \
  --insecure

# Invalid Request - should 403
echo " "
echo " "
echo "------------------------------------------------"
echo "Trying invalid request for aggregates: "
echo "------------------------------------------------"
curl -i 'https://localhost/api/meters/aggregates' \
  -H 'cookie: AuthCookie=rx5NqL9CHlaR6XCJeM_pah-gs9PLrvP7w8pW81w-JHm0nlxroEGD0rZY1FqiDvD_KIW1VWdSNIXd9ETZG-0P8Q==; UserRecord=eyJlbWFpbCI6Imphc29uQGphc29uYWNveC5jb20iLCJmaXJzdG5hbWUiOiJUZXNsYSIsImxhc3RuYW1lIjoiRW5lcmd5Iiwicm9sZXMiOlsiSG9tZV9Pd25lciJdLCJ0b2tlbiI6InJ4NU5xTDlDSGxhUjZYQ0plTV9wYWgtZ3M5UExydlA3dzhwVzgxdy1KSG0wbmx4cm9FR0QwclpZMUZxaUR2RF9LSVcxVldkU05JWGQ5RVRaRy0wUDhRPT0iLCJwcm92aWRlciI6IkJhc2ljIiwibG9naW5UaW1lIjoiMjAyMS0xMC0xNlQwMDoyOTozOS45NDc0NTk3NjMtMDc6MDAifQ==' \
  --compressed \
  --insecure

# Valid Request - should 200
echo " "
echo " "
echo "------------------------------------------------"
echo "Trying valid request for aggregates: "
echo "------------------------------------------------"
curl -i 'https://localhost/api/meters/aggregates' \
  -H 'cookie: AuthCookie=1234567890qwertyuiopasdfghjklZXcvbnm1234567890Qwertyuiopasdfghjklzxcvbnm1234567890qwer==; UserRecord=1234567890qwertyuiopasdfghjklZXcvbnm1234567890Qwertyuiopasdfghjklzxcvbnm1234567890qwer1234567890qwertyuiopasdfghjklZXcvbnm1234567890Qwertyuiopasdfghjklzxcvbnm1234567890qwer1234567890qwertyuiopasdfghjklZXcvbnm1234567890Qwertyuiopasdfghjklzxcvbnm1234567890qwer1234567890qwertyuiopasdfghjklZXcvbnm1234567890Qwertyuiopasdfghjklzxcvbnm1234567890qwer123456==' \
  --compressed \
  --insecure

echo " "
echo " "
echo "------------------------------------------------"
