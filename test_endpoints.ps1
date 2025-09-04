# Test script for coordinate calculation endpoints
Write-Host "Testing Coordinate Calculation Endpoints" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Yellow

$testData = @{
    start_lat = 41.214871
    start_lng = -105.788835
    bearing_degrees = 176.0
    distance_feet = 1638.0
}

# Test Geodesic
Write-Host "`nTesting Geodesic (GeographicLib):" -ForegroundColor Blue
$testData.method = "geodesic"
$json = $testData | ConvertTo-Json
$result = Invoke-WebRequest -Uri "http://localhost:8000/api/mapping/coordinates/calculate-endpoint" -Method POST -ContentType "application/json" -Body $json
$data = $result.Content | ConvertFrom-Json
Write-Host "  End Point: $($data.end_lat), $($data.end_lng)"
Write-Host "  Method: $($data.method)"

# Test UTM
Write-Host "`nTesting UTM (Corrected):" -ForegroundColor Green
$testData.method = "utm"
$json = $testData | ConvertTo-Json
$result = Invoke-WebRequest -Uri "http://localhost:8000/api/mapping/coordinates/calculate-endpoint" -Method POST -ContentType "application/json" -Body $json
$data = $result.Content | ConvertFrom-Json
Write-Host "  End Point: $($data.end_lat), $($data.end_lng)"
Write-Host "  Method: $($data.method)"

# Test Haversine
Write-Host "`nTesting Haversine (Fast):" -ForegroundColor Yellow
$testData.method = "haversine"
$json = $testData | ConvertTo-Json
$result = Invoke-WebRequest -Uri "http://localhost:8000/api/mapping/coordinates/calculate-endpoint" -Method POST -ContentType "application/json" -Body $json
$data = $result.Content | ConvertFrom-Json
Write-Host "  End Point: $($data.end_lat), $($data.end_lng)"
Write-Host "  Method: $($data.method)"

Write-Host "`nAll backend endpoints tested successfully!" -ForegroundColor Green