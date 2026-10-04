#include "mesh_pair.h"

#include <cstring>

#include "mesh_crypto.h"

namespace mesh {

void derive_pair_key(const uint8_t shared[32], const uint8_t remote_mac[kMacLen], const uint8_t master_mac[kMacLen],
                     uint8_t k[32]) {
  static const uint8_t label[] = {'h', 'a', 'r', 'n', 'o', '-', 'p', 'a', 'i', 'r'};
  const Part parts[3] = {{label, sizeof label}, {remote_mac, kMacLen}, {master_mac, kMacLen}};
  hmac_sha256(shared, 32, parts, 3, k);
}

static void xor_pad(const uint8_t k[32], const uint8_t in[32], uint8_t out[32]) {
  static const uint8_t enc[] = {'e', 'n', 'c'};
  uint8_t pad[32];
  hmac_sha256(k, 32, enc, sizeof enc, pad);
  for (int i = 0; i < 32; i++) out[i] = static_cast<uint8_t>(in[i] ^ pad[i]);
}

void make_blob(const uint8_t k[32], const uint8_t mesh_key[16], const uint8_t remote_key[16], uint8_t blob[32]) {
  uint8_t plain[32];
  std::memcpy(plain, mesh_key, 16);
  std::memcpy(plain + 16, remote_key, 16);
  xor_pad(k, plain, blob);
}

void open_blob(const uint8_t k[32], const uint8_t blob[32], uint8_t mesh_key[16], uint8_t remote_key[16]) {
  uint8_t plain[32];
  xor_pad(k, blob, plain);
  std::memcpy(mesh_key, plain, 16);
  std::memcpy(remote_key, plain + 16, 16);
}

#ifndef MESHCORE_EXTERNAL_HMAC
void InsecureTestStubX25519::publicKey(uint8_t pub[32], const uint8_t priv[32]) {
  static const uint8_t tag[] = {'s', 't', 'u', 'b', '-', 'p', 'u', 'b'};
  Sha256 s;
  s.update(tag, sizeof tag);
  s.update(priv, 32);
  s.finish(pub);
}

void InsecureTestStubX25519::sharedSecret(uint8_t out[32], const uint8_t priv[32], const uint8_t peer_pub[32]) {
  uint8_t mine[32];
  publicKey(mine, priv);
  const bool mine_first = std::memcmp(mine, peer_pub, 32) <= 0;
  Sha256 s;
  s.update(mine_first ? mine : peer_pub, 32);
  s.update(mine_first ? peer_pub : mine, 32);
  s.finish(out);
}
#endif

}  // namespace mesh
