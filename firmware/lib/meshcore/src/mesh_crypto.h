// SHA-256 and HMAC-SHA256, small and portable. A device build may replace both with mbedtls: define
// MESHCORE_EXTERNAL_HMAC and provide mesh::hmac_sha256(...) below (the only function the rest of meshcore uses).
#pragma once
#include <cstddef>
#include <cstdint>

namespace mesh {

struct Part {
  const uint8_t* p;
  size_t n;
};

// out = HMAC-SHA256(key, parts[0] || parts[1] || ...)
void hmac_sha256(const uint8_t* key, size_t key_len, const Part* parts, size_t n_parts, uint8_t out[32]);

inline void hmac_sha256(const uint8_t* key, size_t key_len, const uint8_t* msg, size_t msg_len, uint8_t out[32]) {
  const Part one{msg, msg_len};
  hmac_sha256(key, key_len, &one, 1, out);
}

// Constant-time compare.
bool ct_equal(const uint8_t* a, const uint8_t* b, size_t n);

#ifndef MESHCORE_EXTERNAL_HMAC
class Sha256 {
 public:
  Sha256() { reset(); }
  void reset();
  void update(const uint8_t* data, size_t len);
  void finish(uint8_t out[32]);

 private:
  void block(const uint8_t* b);
  uint32_t h_[8];
  uint8_t buf_[64];
  uint64_t total_;
  size_t fill_;
};
#endif

}  // namespace mesh
