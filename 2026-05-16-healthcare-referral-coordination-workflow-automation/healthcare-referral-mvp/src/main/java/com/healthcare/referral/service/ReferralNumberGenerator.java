package com.healthcare.referral.service;

import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.atomic.AtomicLong;

@Component
public class ReferralNumberGenerator {

    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("yyyyMMdd");
    private final AtomicLong sequence = new AtomicLong(1000);

    public String generate() {
        String datePart = LocalDateTime.now().format(FORMATTER);
        long seq = sequence.incrementAndGet();
        return "REF-" + datePart + "-" + String.format("%05d", seq);
    }
}