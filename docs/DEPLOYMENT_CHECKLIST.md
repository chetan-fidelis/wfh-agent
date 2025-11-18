# Deployment Checklist - v0.1.19 (Download Monitor)

## Pre-Deployment

### Code Review
- [ ] Review `download_monitor.py` for security issues
- [ ] Verify all designations are correctly spelled in `emp_monitor.py`
- [ ] Check error handling and logging in monitor startup
- [ ] Confirm auth token handling doesn't expose secrets

### Dependencies
- [ ] Verify `requests` library is in `requirements.txt`
- [ ] Check Python version compatibility (3.8+)
- [ ] Test imports on target Python version

### Configuration
- [ ] Update `monitor_data/config.json` with download_monitor section
- [ ] Set `enabled: false` initially (enable per-employee)
- [ ] Verify API endpoint URL is correct
- [ ] Test auth token format

## Build & Package

### Backend
```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Run tests (if available)
python -m pytest tests/ -v

# Build PyInstaller spec
pyinstaller emp_monitor.spec --clean --noconfirm
```

### Electron App
```bash
# Build backend
npm run build:backend

# Build Electron
npm run build:electron

# Verify package includes download_monitor.py
# Check: dist/emp_monitor_backend/download_monitor.py exists
```

### Verification Checklist
- [ ] `download_monitor.py` is in packaged backend
- [ ] `emp_monitor.py` includes download monitor initialization
- [ ] Config template includes download_monitor section
- [ ] No hardcoded secrets in code
- [ ] Version bumped to 0.1.19 in `package.json`

## Staging Deployment

### Test Environment Setup
1. **Create test user with recruitment designation**
   ```json
   {
     "emp_id": 999,
     "designation": "Manager - Talent Acquisition",
     "download_monitor": {
       "enabled": true,
       "api_url": "http://staging-ats.test/api"
     }
   }
   ```

2. **Set auth token**
   ```powershell
   $env:CV_CAPTURE_AUTH_TOKEN = "test-token-123"
   ```

3. **Launch app and verify startup logs**
   ```
   [DownloadMonitor] Monitoring 5 download paths
   [DownloadMonitor] Monitor thread started
   ```

### Functional Testing
- [ ] Download a test file: `Naukri_Test_CV.pdf`
- [ ] Verify file is detected in logs
- [ ] Confirm presign API is called
- [ ] Check S3 upload succeeds
- [ ] Verify metadata is stored
- [ ] Test duplicate file detection (re-download same file)
- [ ] Verify file is not re-uploaded

### Edge Cases
- [ ] Test with file still being written (should wait)
- [ ] Test with oversized file (should skip)
- [ ] Test with wrong extension (should skip)
- [ ] Test with wrong filename pattern (should skip)
- [ ] Test with no auth token (should log warning)
- [ ] Test with unreachable API (should log error)

### Performance Testing
- [ ] Monitor CPU usage during scan (should be <1%)
- [ ] Check memory usage (should be <20MB)
- [ ] Verify no impact on other features
- [ ] Test with 100+ files in download folder

## Production Deployment

### Pre-Release
- [ ] Update version to 0.1.19 in `package.json`
- [ ] Update `CHANGELOG.md` with new features
- [ ] Create GitHub release with assets
- [ ] Tag commit: `v0.1.19`

### Rollout Strategy
1. **Phase 1: Internal Testing (1 week)**
   - Deploy to 5-10 internal recruitment staff
   - Monitor logs for errors
   - Collect feedback

2. **Phase 2: Pilot (1-2 weeks)**
   - Deploy to 20-30 pilot users
   - Monitor API load and S3 usage
   - Verify data quality

3. **Phase 3: Full Rollout**
   - Enable for all recruitment-related employees
   - Monitor for 1 week post-deployment
   - Have rollback plan ready

### Deployment Steps
1. **Update GitHub Release**
   ```bash
   git tag v0.1.19
   git push origin v0.1.19
   # Upload: latest.yml, installer.exe, installer.exe.blockmap
   ```

2. **Notify Users**
   - Send email about new feature
   - Include setup instructions
   - Provide support contact

3. **Monitor First 24 Hours**
   - Check error logs for crashes
   - Monitor API endpoint performance
   - Track file upload success rate
   - Watch for duplicate uploads

## Configuration Management

### Per-Employee Enablement
```json
{
  "emp_id": 123,
  "designation": "Senior Executive - Talent Acquisition",
  "download_monitor": {
    "enabled": true,
    "api_url": "http://ats-tool.test/api",
    "check_interval_sec": 30
  }
}
```

### Environment Variables
```powershell
# Required for download monitor to work
$env:CV_CAPTURE_AUTH_TOKEN = "your-sanctum-token"

# Optional: override API URL
$env:CV_CAPTURE_API_URL = "http://ats-tool.test/api"
```

### Rollback Configuration
If issues arise, disable immediately:
```json
{
  "download_monitor": {
    "enabled": false
  }
}
```

## Monitoring & Logging

### Key Metrics to Track
- **Upload Success Rate**: Target >95%
- **Average Upload Time**: Should be <5 seconds
- **File Detection Latency**: Should be <60 seconds
- **API Error Rate**: Should be <1%

### Log Locations
- **App Logs**: `monitor_data/alerts.log`
- **System Logs**: Windows Event Viewer
- **API Logs**: Laravel application logs

### Alert Thresholds
- [ ] Set up alert if upload success rate drops below 90%
- [ ] Alert if API response time exceeds 10 seconds
- [ ] Alert if more than 5 consecutive upload failures

## Post-Deployment

### Day 1
- [ ] Verify no critical errors in logs
- [ ] Check API endpoint is responding
- [ ] Confirm files are being uploaded
- [ ] Monitor system resource usage

### Week 1
- [ ] Analyze upload patterns
- [ ] Check data quality in database
- [ ] Gather user feedback
- [ ] Review performance metrics

### Month 1
- [ ] Generate usage report
- [ ] Identify optimization opportunities
- [ ] Plan next iteration
- [ ] Document lessons learned

## Rollback Plan

### If Critical Issues Occur
1. **Immediate**: Disable in config
   ```json
   {"download_monitor": {"enabled": false}}
   ```

2. **Notify Users**: Send alert about temporary disable

3. **Investigate**: Check logs for root cause

4. **Fix & Test**: Apply fix and re-test in staging

5. **Redeploy**: Push fixed version

### Rollback Checklist
- [ ] Disable download monitor in config
- [ ] Verify no orphaned threads
- [ ] Check for stuck file locks
- [ ] Clear processed file cache if needed
- [ ] Restart backend service

## Support & Documentation

### User Documentation
- [ ] Create FAQ for recruitment staff
- [ ] Document supported file types
- [ ] Explain what happens to uploaded files
- [ ] Provide troubleshooting guide

### Admin Documentation
- [ ] Configuration guide
- [ ] Monitoring guide
- [ ] Troubleshooting guide
- [ ] API integration guide

### Support Contacts
- **Technical Issues**: DevOps team
- **API Issues**: Backend team
- **User Issues**: HR/Recruitment team

## Sign-Off

- [ ] QA Lead: Approved for production
- [ ] DevOps Lead: Infrastructure ready
- [ ] Product Owner: Feature complete
- [ ] Security: No vulnerabilities found

**Deployment Date**: _______________
**Deployed By**: _______________
**Approved By**: _______________
