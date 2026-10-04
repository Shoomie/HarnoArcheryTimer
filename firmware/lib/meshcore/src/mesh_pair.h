// Pairing key derivation (docs/mesh.md section 5). X25519 sits behind an interface: PortableX25519 (RFC 7748,
// mesh_x25519.cpp) is the real implementation; InsecureTestStubX25519 is symmetric but NOT secure: tests only.
#pragma once
#include <cstdint>

#include "mesh_frame.h"

namespace mesh {

// K = HMAC-SHA256(shared, "harno-pair" || remote_mac(6) || master_mac(6))
void derive_pair_key(const uint8_t shared[32], const uint8_t remote_mac[kMacLen], const uint8_t master_mac[kMacLen],
                     uint8_t k[32]);

// blob = (mesh_key || remote_key) XOR HMAC-SHA256(K, "enc")   (the same call decrypts: pass the blob as input)
void make_blob(const uint8_t k[32], const uint8_t mesh_key[16], const uint8_t remote_key[16], uint8_t blob[32]);
void open_blob(const uint8_t k[32], const uint8_t blob[32], uint8_t mesh_key[16], uint8_t remote_key[16]);

class X25519 {
 public:
  virtual ~X25519() = default;
  virtual void publicKey(uint8_t pub[32], const uint8_t priv[32]) = 0;                         // priv * basepoint
  virtual void sharedSecret(uint8_t out[32], const uint8_t priv[32], const uint8_t peer_pub[32]) = 0;
};

// Real X25519 (RFC 7748), TweetNaCl-style, no dependencies, constant-time field arithmetic (no secret-dependent
// branches or indexes). The private key is any 32 random bytes (clamped inside). The caller supplies the randomness
// (device: esp_fill_random / hardware RNG with the radio on) and should reject an all-zero shared secret
// (low-order peer key): see x25519_is_zero().
class PortableX25519 : public X25519 {
 public:
  void publicKey(uint8_t pub[32], const uint8_t priv[32]) override;
  void sharedSecret(uint8_t out[32], const uint8_t priv[32], const uint8_t peer_pub[32]) override;
};

// out = scalar * u (RFC 7748 X25519 function, scalar clamped inside). Free function for tests and callers.
void x25519(uint8_t out[32], const uint8_t scalar[32], const uint8_t u[32]);
bool x25519_is_zero(const uint8_t v[32]);  // constant time

// Symmetric stand-in: pub = SHA-256("stub-pub" || priv), shared = SHA-256(min(pubs) || max(pubs)).
// Insecure on purpose; never ship it.
class InsecureTestStubX25519 : public X25519 {
 public:
  void publicKey(uint8_t pub[32], const uint8_t priv[32]) override;
  void sharedSecret(uint8_t out[32], const uint8_t priv[32], const uint8_t peer_pub[32]) override;
};

}  // namespace mesh
