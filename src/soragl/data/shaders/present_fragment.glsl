#version 330 core

uniform sampler2D u_surface;
uniform vec2 u_surface_size;
// output pixels per surface pixel; 0 disables sharpening (plain filtering)
uniform vec2 u_scale;

in vec2 f_uv;
out vec4 f_color;

void main() {
    vec2 uv = f_uv;
    if (u_scale.x > 0.0) {
        // "sharp bilinear": nearest inside each source pixel, a one-output-pixel
        // linear blend at its edges, so non-integer scales stay crisp and even
        vec2 texel = f_uv * u_surface_size;
        vec2 from_center = fract(texel) - 0.5;
        vec2 flat_region = 0.5 - 0.5 / u_scale;
        vec2 blend = (from_center - clamp(from_center, -flat_region, flat_region)) * u_scale + 0.5;
        uv = (floor(texel) + blend) / u_surface_size;
    }
    f_color = vec4(texture(u_surface, uv).rgb, 1.0);
}
