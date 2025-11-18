# Laravel API Integration Guide - CV Capture

## Overview

The Electron app's Download Monitor integrates with the Laravel CV Capture API to upload Naukri CVs. This guide documents the required API endpoints and integration points.

## Required API Endpoints

### 1. Authentication

**Endpoint**: `POST /api/cv-capture/auth/login`

Request:
```json
{
  "email": "user@example.com",
  "password": "password"
}
```

Response:
```json
{
  "token": "sanctum-token-here",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "User Name"
  }
}
```

**Note**: The app uses Bearer token authentication. Ensure Sanctum is configured.

---

### 2. Presign S3 URL

**Endpoint**: `POST /api/cv-capture/presign`

**Authentication**: Bearer token (required)

Request:
```json
{
  "file_name": "Naukri_John_Doe.pdf",
  "file_size": 245000
}
```

Response:
```json
{
  "url": "https://s3-bucket.s3.amazonaws.com/cv-capture/...",
  "id": "metadata-record-id",
  "expires_in": 900
}
```

**Implementation Notes**:
- Generate presigned URL valid for 15 minutes (900 seconds)
- Store metadata record and return its ID
- URL should allow PUT requests with `Content-Type: application/octet-stream`
- Include S3 bucket path prefix (e.g., `cv-capture/`)

**Laravel Example**:
```php
use Aws\S3\S3Client;

Route::post('/cv-capture/presign', function (Request $request) {
    $request->validate([
        'file_name' => 'required|string|max:255',
        'file_size' => 'required|integer|max:104857600' // 100MB
    ]);
    
    $s3 = new S3Client([
        'version' => 'latest',
        'region'  => env('AWS_DEFAULT_REGION'),
    ]);
    
    $cmd = $s3->getCommand('PutObject', [
        'Bucket' => env('AWS_BUCKET'),
        'Key'    => 'cv-capture/' . time() . '_' . $request->file_name,
    ]);
    
    $request_obj = $s3->createPresignedRequest($cmd, '+20 minutes');
    $presigned_url = (string)$request_obj->getUri();
    
    // Store metadata record
    $metadata = CVCaptureMetadata::create([
        'emp_id' => auth()->id(),
        'file_name' => $request->file_name,
        'file_size' => $request->file_size,
        's3_key' => 'cv-capture/' . time() . '_' . $request->file_name,
        'status' => 'pending'
    ]);
    
    return response()->json([
        'url' => $presigned_url,
        'id' => $metadata->id,
        'expires_in' => 900
    ]);
})->middleware('auth:sanctum');
```

---

### 3. Store Metadata

**Endpoint**: `POST /api/cv-capture/metadata`

**Authentication**: Bearer token (required)

Request:
```json
{
  "file_name": "Naukri_John_Doe.pdf",
  "file_size": 245000,
  "file_hash": "sha256-hash-here",
  "download_path": "C:\\Users\\...",
  "uploaded_at": "2025-11-06T16:30:00Z",
  "emp_id": 123
}
```

Response:
```json
{
  "id": "metadata-record-id",
  "emp_id": 123,
  "file_name": "Naukri_John_Doe.pdf",
  "file_size": 245000,
  "file_hash": "sha256-hash",
  "status": "uploaded",
  "uploaded_at": "2025-11-06T16:30:00Z",
  "created_at": "2025-11-06T16:30:01Z"
}
```

**Implementation Notes**:
- Update metadata record created during presign
- Mark status as "uploaded"
- Store file hash for deduplication
- Record upload timestamp

**Laravel Example**:
```php
Route::post('/cv-capture/metadata', function (Request $request) {
    $request->validate([
        'file_name' => 'required|string',
        'file_size' => 'required|integer',
        'file_hash' => 'required|string|size:64', // SHA256
        'download_path' => 'nullable|string',
        'uploaded_at' => 'required|date_format:Y-m-d\TH:i:s\Z',
        'emp_id' => 'required|integer'
    ]);
    
    $metadata = CVCaptureMetadata::updateOrCreate(
        ['file_hash' => $request->file_hash],
        [
            'emp_id' => $request->emp_id,
            'file_name' => $request->file_name,
            'file_size' => $request->file_size,
            'download_path' => $request->download_path,
            'status' => 'uploaded',
            'uploaded_at' => $request->uploaded_at
        ]
    );
    
    return response()->json($metadata, 201);
})->middleware('auth:sanctum');
```

---

### 4. Get Metadata

**Endpoint**: `GET /api/cv-capture/metadata/{id}`

**Authentication**: Bearer token (required)

Response:
```json
{
  "id": "metadata-record-id",
  "emp_id": 123,
  "file_name": "Naukri_John_Doe.pdf",
  "file_size": 245000,
  "file_hash": "sha256-hash",
  "s3_key": "cv-capture/1234567890_Naukri_John_Doe.pdf",
  "status": "uploaded",
  "uploaded_at": "2025-11-06T16:30:00Z",
  "created_at": "2025-11-06T16:30:01Z"
}
```

---

### 5. Admin: List Uploads

**Endpoint**: `GET /api/cv-capture/admin/uploads`

**Authentication**: Bearer token + admin role (required)

Query Parameters:
- `per_page`: Items per page (default: 50)
- `page`: Page number (default: 1)
- `emp_id`: Filter by employee ID (optional)
- `date_from`: Filter by date (optional)
- `date_to`: Filter by date (optional)

Response:
```json
{
  "data": [
    {
      "id": "metadata-id",
      "emp_id": 123,
      "emp_name": "John Doe",
      "file_name": "Naukri_John_Doe.pdf",
      "file_size": 245000,
      "status": "uploaded",
      "uploaded_at": "2025-11-06T16:30:00Z"
    }
  ],
  "pagination": {
    "total": 150,
    "per_page": 50,
    "current_page": 1,
    "last_page": 3
  }
}
```

---

### 6. Admin: Statistics

**Endpoint**: `GET /api/cv-capture/admin/stats`

**Authentication**: Bearer token + admin role (required)

Response:
```json
{
  "total_uploads": 1250,
  "total_size_mb": 3450,
  "uploads_today": 45,
  "uploads_this_week": 320,
  "uploads_this_month": 1200,
  "unique_employees": 85,
  "average_file_size_kb": 2760,
  "success_rate_percent": 98.5,
  "last_upload": "2025-11-06T16:30:00Z"
}
```

---

### 7. Admin: Delete Upload

**Endpoint**: `DELETE /api/cv-capture/admin/uploads/{id}`

**Authentication**: Bearer token + admin role (required)

Response:
```json
{
  "message": "Upload deleted successfully",
  "id": "metadata-id"
}
```

---

## Database Schema

### CVCaptureMetadata Table

```sql
CREATE TABLE cv_capture_metadata (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    emp_id BIGINT UNSIGNED NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,
    file_hash VARCHAR(64) UNIQUE NOT NULL,
    s3_key VARCHAR(512) NOT NULL,
    download_path VARCHAR(512) NULLABLE,
    status ENUM('pending', 'uploaded', 'failed') DEFAULT 'pending',
    uploaded_at TIMESTAMP NULLABLE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (emp_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_emp_id (emp_id),
    INDEX idx_status (status),
    INDEX idx_uploaded_at (uploaded_at),
    INDEX idx_file_hash (file_hash)
);
```

---

## Error Handling

### Common Error Responses

**400 Bad Request**
```json
{
  "message": "Validation failed",
  "errors": {
    "file_name": ["The file_name field is required"]
  }
}
```

**401 Unauthorized**
```json
{
  "message": "Unauthenticated"
}
```

**403 Forbidden**
```json
{
  "message": "Unauthorized action"
}
```

**404 Not Found**
```json
{
  "message": "Resource not found"
}
```

**413 Payload Too Large**
```json
{
  "message": "File size exceeds maximum allowed (100MB)"
}
```

**500 Internal Server Error**
```json
{
  "message": "An error occurred while processing your request"
}
```

---

## Security Considerations

### 1. Authentication
- Use Laravel Sanctum for token-based authentication
- Tokens should expire after 24 hours
- Implement token refresh mechanism

### 2. Authorization
- Verify employee owns the uploaded file
- Restrict admin endpoints to admin role
- Log all admin actions

### 3. File Validation
- Validate file size on server (max 100MB)
- Verify file hash matches uploaded content
- Scan files for malware before storing

### 4. S3 Security
- Use presigned URLs with 15-minute expiration
- Enable S3 bucket encryption
- Restrict S3 bucket access to application IAM role
- Enable S3 versioning for audit trail

### 5. Data Privacy
- Encrypt sensitive metadata in database
- Implement data retention policy
- Allow employees to delete their own uploads
- Log access to uploaded files

---

## Testing

### Unit Tests

```php
// Test presign endpoint
public function test_presign_returns_valid_url()
{
    $response = $this->actingAs($user)->postJson('/api/cv-capture/presign', [
        'file_name' => 'Naukri_Test.pdf',
        'file_size' => 100000
    ]);
    
    $response->assertStatus(200);
    $response->assertJsonStructure(['url', 'id', 'expires_in']);
}

// Test metadata storage
public function test_metadata_stores_successfully()
{
    $response = $this->actingAs($user)->postJson('/api/cv-capture/metadata', [
        'file_name' => 'Naukri_Test.pdf',
        'file_size' => 100000,
        'file_hash' => 'abc123...',
        'uploaded_at' => now()->toIso8601String(),
        'emp_id' => $user->id
    ]);
    
    $response->assertStatus(201);
    $this->assertDatabaseHas('cv_capture_metadata', [
        'file_hash' => 'abc123...'
    ]);
}
```

### Integration Tests

```bash
# Test full upload flow
1. Call presign endpoint
2. Upload file to S3 using presigned URL
3. Call metadata endpoint
4. Verify file in S3
5. Verify metadata in database
```

---

## Monitoring

### Metrics to Track
- API response times
- Upload success rate
- S3 upload failures
- Database query performance
- Auth token expiration rate

### Alerts
- Alert if upload success rate < 95%
- Alert if API response time > 5 seconds
- Alert if S3 errors > 1% of uploads
- Alert on unauthorized access attempts

---

## Troubleshooting

### Issue: Presign endpoint returns 401
**Solution**: Verify auth token is valid and not expired

### Issue: S3 upload fails with 403
**Solution**: Check IAM role permissions for S3 bucket

### Issue: Metadata not storing
**Solution**: Verify database connection and table exists

### Issue: Files not appearing in admin panel
**Solution**: Check emp_id matches authenticated user

---

## Deployment Checklist

- [ ] Database migrations run successfully
- [ ] S3 bucket created and configured
- [ ] IAM role has S3 permissions
- [ ] Sanctum configured for API authentication
- [ ] CORS configured for Electron app
- [ ] Rate limiting configured
- [ ] Error logging configured
- [ ] Monitoring and alerts set up
- [ ] Backup strategy implemented
- [ ] Security audit completed
