package com.healthcare.referral.repository;

import com.healthcare.referral.domain.entity.ReferralStateHistory;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ReferralStateHistoryRepository extends JpaRepository<ReferralStateHistory, Long> {

    List<ReferralStateHistory> findByReferralIdOrderByPerformedAtAsc(Long referralId);
}